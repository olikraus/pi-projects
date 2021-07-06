

from picamera import PiCamera
from picamera.array import PiRGBArray
from datetime import datetime
import numpy as np
import cv2
import os
import io
import json
import jellyfish

import smbus
import time
import argparse





eject_motor_adr = 0x65
sorter_motor_adr = 0x60

eject_motor_shake_speed = 40     # 0..63
eject_motor_throw_out_speed = 50 # 0..63
eject_motor_throw_out_time = 0.27

sorter_motor_basket_0_1_speed = 15      # 0..63, speed should be very low, however a minimal speed is required (>9)
sorter_motor_basket_0_1_time = 0.25      # time in seconds

sorter_motor_basket_2_3_speed = 63      # 0..63, speed should be very high
sorter_motor_basket_2_3_time = 0.8      # time in seconds

jpeg_full_image_quality=10      # 0..100


parser = argparse.ArgumentParser(description='Card Sorter Machine Controller', formatter_class=argparse.RawTextHelpFormatter)


# DRV8830
#	Register 0: 	vvvvvvbb
#	Register 1:	c--4321f
#
#	bb = 00		coast
#	bb = 01		reverse
#	bb = 10		forward
#	bb = 11		break
# around one second is required to reach full speed (from 0 to 63)

def motor_coast(adr):
	bus = smbus.SMBus(1)
	bus.write_byte_data(adr, 1, 0x80)	# clear any faults
	bus.write_byte_data(adr, 0, 0)	# send coast

def motor_break(adr):
	bus = smbus.SMBus(1)
	bus.write_byte_data(adr, 1, 0x80)	# clear any faults
	bus.write_byte_data(adr, 0, 3)	# send coast

# dir = 0: reverse, dir = 1: forward
# speed = 0..63
def motor_run(adr,speed,dir):
	bus = smbus.SMBus(1)
	bus.write_byte_data(adr, 1, 0x80)	# clear any faults
	bus.write_byte_data(adr, 0, speed*4 + 1+dir)	# drive
	
# cnt: number of shakes for the eject motor
# d1: forward drive duration
# d2: backward drive duration
def eject_motor_shake(cnt, d1, d2):
	for i in range(cnt):
		motor_run(eject_motor_adr, eject_motor_shake_speed, 0)
		time.sleep(d1)
		motor_break(eject_motor_adr)
		time.sleep(0.01)
		motor_run(eject_motor_adr, eject_motor_shake_speed, 1)
		time.sleep(d2)
		motor_break(eject_motor_adr)
		time.sleep(0.01)

def clean_str(s):
  t = ''
  for c in s:
    if c >= 'A' and c <=  'Z':
      t += c
    elif c >= 'a' and c <= 'z':
      t+= c
    else:
      t+='_'
  return t
  
def card_eject():
	# try to separate lowest card
	eject_motor_shake(8, 0.05, 0.05)
	eject_motor_shake(24, 0.05, 0.04)

	# throw out lowest card
	motor_run(eject_motor_adr, eject_motor_throw_out_speed, 0)
	time.sleep(eject_motor_throw_out_time)
	motor_coast(eject_motor_adr)
	time.sleep(0.6)

	# pull back second lowest card
	# motor_run(eject_motor_adr, 25, 1)
	motor_run(eject_motor_adr, 25, 1)
	time.sleep(0.1)
	eject_motor_shake(10, 0.06, 0.08)
	motor_run(eject_motor_adr, 25, 1)
	# in parallel shake card in the sorter and pull back the second lowest card
	#for i in range(6):
	#	motor_run(sorter_motor_adr, 15, 0)
	#	time.sleep(0.025)
	#	motor_break(sorter_motor_adr)
	#	time.sleep(0.01)
	#	motor_run(sorter_motor_adr, 15, 1)
	#	time.sleep(0.025)
	#	motor_break(sorter_motor_adr)
	#	time.sleep(0.01)
	
        # continue with pullback
	time.sleep(0.5)
	# stop pullback
	motor_coast(eject_motor_adr)
	time.sleep(0.1)

def card_sort(basket):
  dir = 1
  # try to move the the card a little bit into the desired direction
  #motor_run(sorter_motor_adr,7,dir)
  #time.sleep(0.04)
  #motor_break(sorter_motor_adr)
  #time.sleep(0.3)
  #motor_run(sorter_motor_adr,7,1-dir)
  #time.sleep(0.03)
  #motor_break(sorter_motor_adr)
  #time.sleep(0.1)
  #motor_run(sorter_motor_adr,7,dir)
  #time.sleep(0.04)
  #motor_break(sorter_motor_adr)
  #time.sleep(0.3)
  # after this throw out the card with very low or very high speed
  if (basket & 2) == 0:
    # try to move the the card a little bit into the desired direction
    motor_run(sorter_motor_adr,7,dir)
    time.sleep(0.04)
    motor_break(sorter_motor_adr)
    time.sleep(0.3)
    motor_run(sorter_motor_adr,7,1-dir)
    time.sleep(0.03)
    motor_break(sorter_motor_adr)
    time.sleep(0.1)
  
    motor_run(sorter_motor_adr, sorter_motor_basket_0_1_speed, dir)
    time.sleep(sorter_motor_basket_0_1_time)
    motor_coast(sorter_motor_adr)
    time.sleep(0.3)
    
    # do another attempt in cases that the first throwout didn't work
    motor_run(sorter_motor_adr,7,1-dir)
    time.sleep(0.03)
    motor_break(sorter_motor_adr)
    time.sleep(0.1)
  
    motor_run(sorter_motor_adr, sorter_motor_basket_0_1_speed, dir)
    time.sleep(sorter_motor_basket_0_1_time)
    motor_coast(sorter_motor_adr)
    time.sleep(0.1)
  else:
    motor_run(sorter_motor_adr, sorter_motor_basket_2_3_speed, dir)
    time.sleep(sorter_motor_basket_2_3_time)
    motor_coast(sorter_motor_adr)
    time.sleep(0.1)

# https://stackoverflow.com/questions/46390779/automatic-white-balancing-with-grayworld-assumption

def white_balance(img):
    result = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    avg_a = np.average(result[:, :, 1])
    avg_b = np.average(result[:, :, 2])
    result[:, :, 1] = result[:, :, 1] - ((avg_a - 128) * (result[:, :, 0] / 255.0) * 1.1)
    result[:, :, 2] = result[:, :, 2] - ((avg_b - 128) * (result[:, :, 0] / 255.0) * 1.1)
    result = cv2.cvtColor(result, cv2.COLOR_LAB2BGR)
    return result

def remove_barrel_distortion(img):
	bordersize = 32
	src = cv2.copyMakeBorder(
	    img,
	    top=bordersize,
	    bottom=bordersize,
	    left=bordersize,
	    right=bordersize,
	    borderType=cv2.BORDER_CONSTANT,
	    value=[0, 0, 0]
	)

	# remove the barrel distortion

	width  = src.shape[1]
	height = src.shape[0]

	distCoeff = np.zeros((4,1),np.float64)

	k1 = -1.2e-5; # negative to remove barrel distortion
	k2 = 0.0;
	p1 = 0.0;
	p2 = 0.0;

	distCoeff[0,0] = k1;
	distCoeff[1,0] = k2;
	distCoeff[2,0] = p1;
	distCoeff[3,0] = p2;

	# assume unit matrix for camera
	cam = np.eye(3,dtype=np.float32)

	cam[0,2] = width/2.0  # define center x
	cam[1,2] = height/2.0 # define center y
	cam[0,0] = 10.        # define focal length x
	cam[1,1] = 10.        # define focal length y

	# here the undistortion will be computed
	dst = cv2.undistort(src,cam,distCoeff)
	return dst

def read_file(filename):
	f = open(filename)
	s = f.read()
	f.close()
	return s

def append_to_file(filename, s):
	f = open(filename, "a")
	f.write(s)
	f.close()

def read_json(filename):
  f = io.open(filename, "r", encoding=None)
  obj = json.load(f)
  f.close()
  return obj

def cam_capture(cam, imagename, fullimname):
  rawCapture = PiRGBArray(cam)
  #camera.capture('image.jpg')
  cam.capture(rawCapture, format="bgr")
  # remove the barrel distortion of the raspi cam
  #image = remove_barrel_distortion(white_balance(rawCapture.array))
  image = remove_barrel_distortion(rawCapture.array)
  # write a low quality picture of the scanned card
  cv2.imwrite(fullimname, image,[cv2.IMWRITE_JPEG_QUALITY, jpeg_full_image_quality, cv2.IMWRITE_JPEG_LUMA_QUALITY, jpeg_full_image_quality]);
  #image = rawCapture.array;
  image = image[0:135, 0:1279]
  # https://stackoverflow.com/questions/9480013/image-processing-to-improve-tesseract-ocr-accuracy
  image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
  #(thresh, blackAndWhiteImage) = cv2.threshold(image, 120, 255, cv2.THRESH_BINARY)

  kernel = np.ones((3, 3), np.uint8)
  img = cv2.dilate(image, kernel, iterations=1)
  img = cv2.erode(img, kernel, iterations=1)	
  img = cv2.adaptiveThreshold(cv2.medianBlur(img, 3), 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 63, 4)
  
  cv2.imwrite('raw_'+imagename, image);
  cv2.imwrite(imagename, img);
  #cv2.imwrite('image_bw_'+str(i)+'.jpg', blackAndWhiteImage);
  # tesseract --dpi 500 --psm 6 image_g_XX.jpg stdout

def avg(list):
    return sum(list) / len(list)

# return the result from tesseract
def get_ocr_card_name(imagefile):
  # execute tesseract
  os.system("tesseract --dpi 500 --psm 6 " + imagefile +" out txt")  # write to out.txt

  # character based updates
  ocr_result = read_file('out.txt')
  ocr_result = ocr_result.replace(chr(8212), "")          # big dash, created by tesseract
  ocr_result = ocr_result.replace("_", " ")          # replace underscore with blank
  ocr_result = ocr_result.replace("~", "")          # remove tilde
  ocr_result = ocr_result.replace(".", " ")          # replace  dot with blank
  ocr_result = ocr_result.replace("@", "")          # remove @
  
  # find the line which contains the card name with highest probability
  ocr_lines = ocr_result.split("\n")      # split into lines
  ocr_lines = list(map(lambda s: s.split(" "), ocr_lines))        # split lines into words
  ocr_lines = list(map(lambda l : list(filter(lambda s: len(s) > 2, l)), ocr_lines  )) # remove words with 1 or 2 chars
  ocr_lines = list(filter(lambda l : len(l) > 0, ocr_lines))       # remove lines which are now empty
  ocr_hist = list(map(lambda l : list(map(lambda s: len(s), l)), ocr_lines))  # replace all strings by their string length
  ocr_hist = list(map(lambda l : avg(l), ocr_hist))       # calculate the average word size
  line_index = ocr_hist.index(max(ocr_hist))                  # get the line index with the highest average word size
  ocr_name = " ".join(ocr_lines[line_index])
  
  # log some data to the log file
  append_to_file("drv_and_cam.log", str(ocr_lines)+"\n")
  append_to_file("drv_and_cam.log", str(ocr_hist)+": "+ ocr_name + "\n")
  return ocr_name
  
# return a vector with the internal card id, the card name and the distance to the tesseract name
def find_card(carddic, ocr_name):
  t = { 
  8209: 45, 8211:45, # convert dash
  48: 111, 79: 111, # convert zero and uppercase O to small o
  211: 111, 212: 111, 214: 111, # other chars similar to o
  242: 111, 243: 111, 244: 111, 245: 111, 246: 111, # other chars similar to o
  959:111, 1086:111, 8009:111, 1054:111,    # other chars similar to o
  73:105, 74:105, 106:105, 108:105, 124:105, # convert upper i, upper j, small j, small l and pipe symbol to small i
  161:105, 205:105, 206:105, 236:105, 237:105, 238:105, 239:105, 1575:105,  # convert other chars to i
  192: 65, 193: 65, 194: 65, 196: 65, 1040:65, 1044:65,         # upper A
  200: 69, 201: 69, 202: 69, 1045:69,   # upper E
  85:117,  # convert upper U to small u
  218: 117, 220: 117,  # other conversions to small u
  249: 117, 250: 117, 251: 117, 252: 117, # other conversions to small u
  956: 117, 1094: 117,
  224: 97, 225: 97, 226: 97, 227: 97, 228: 97, 229: 97, # small a conversion
  232: 101, 233: 101, 234: 101, 235: 101 # small e conversion
  }

  d = 999
  dmin = 999
  smin = ""
  n = ocr_name.translate(t)
  for c in carddic:
    #d = jellyfish.levenshtein_distance(c.translate(t), n)
    d = jellyfish.levenshtein_distance(c, ocr_name)
    if dmin > d:
      dmin = d
      smin = c
      print(c + "/"+ ocr_name+" "+str(d))
      #print(c.translate(t) + "/"+ ocr_name.translate(t))
      
  append_to_file("drv_and_cam.log", "--> "+ smin + " (" + str(carddic[smin]) + ")\n")
  return [carddic[smin], smin, dmin]

def eval_cond(cond, prop):
  tc = prop["tc"]       # Creature
  ts = prop["ts"]       # Sorcery
  ti = prop["ti"]       # Instant
  ta = prop["ta"]       # Artefact
  tl = prop["tl"]       # Land
  te = prop["te"]       # Enhancement
  tp = prop["tp"]       # Planeswalker
  cmc = prop["c"]
  r = prop["r"]                 # rarity 0=common, 1=uncommon, 2=rare, 3=mythic
  cw = "W" in prop["i"]
  cb = "B" in prop["i"]
  cr = "R" in prop["i"]
  cg = "G" in prop["i"]
  cu = "U" in prop["i"]
  #print('cmc='+str(cmc))
  return eval(cond)

def get_basket_number(prop):
  if eval_cond(args.b0c, prop):
    return 0
  if eval_cond(args.b1c, prop):
    return 1
  if eval_cond(args.b2c, prop):
    return 2
  return 3
  
  
def sort_machine():
  card_dic = read_json('mtg_card_dic.json')
  card_prop = read_json('mtg_card_prop.json')


  camera = PiCamera()

  # camera.flash_mode = 'on'
  camera.start_preview()
  camera.exposure_mode = 'night'
  # camera.exposure_compensation = 0
  camera.brightness = 60	# default: 50
  camera.contrast = 100     # default: 0
  #camera.rotation = 0
  #camera.resolution = (1280, 1024)
  camera.rotation = 90
  camera.resolution = (1024,1280)
  #camera.resolution = (480,640)


  for i in range(1):
    card_eject()
    time.sleep(0.4)

    t = time.time()
    strdt = datetime.now().strftime("%Y_%m_%d_%H%M%S")
    cam_capture(camera, 'image.jpg', strdt+'.jpg')
    t_cam = time.time()
    ocr_name = get_ocr_card_name('image.jpg')
    t_ocr = time.time()
    cardv = find_card(card_dic, ocr_name)
    t_find = time.time()
   
    os.rename(strdt+'.jpg', strdt+'_'+clean_str( cardv[1] )+'.jpg')
    #print( cardv[1] )
    #print( clean_str( cardv[1] ))
    basket_number = get_basket_number(card_prop[cardv[0]])
    print(basket_number)
    card_sort(0)
    append_to_file("drv_and_cam.log", "cam: "+str(t_cam-t)+', ocr: '+str(t_ocr - t_cam)+', find: '+str(t_find-t_ocr)  )
    
  camera.stop_preview()

parser.add_argument('-c',
                    default='all',
                    const='all',
                    nargs='?',
                    choices=['eb', 'em', 'sm', 'tc', 'all'],
                    help='''Define command to execute (default: %(default)s)
    eb: Eject a card into sorter and move the card into a basket (uses -b and -r)
    tc: test basket conditions b0c, b1c and b2c
      Allowed variabls in conditions:
        tc: Creature?
        ts: Sorcery?
        ti: Instant?
        ta: Artifact?
        tl: Land?
        te: Enchantment?
        tp: Planeswalker?
        cmc: Converted mana cost
        r: rarity 0=common, 1=uncommon, 2=rare, 3=mythic
        cw: Is white card?
        cb: Is black card?
        cr: Is red card?
        cg: Is green card?
        cu: Is blue card?
''')
parser.add_argument('-b', 
  action='store',
  nargs='?', 
  default=0,
  const=0,
  type=int,
  help='target basket number')
parser.add_argument('-r',  action='store', nargs='?',  default=1, const=1, type=int, help='repeat count (for -c em)')
parser.add_argument('-b0c',  action='store', nargs='?',  default='tc', help='basket 0 condition')
parser.add_argument('-b1c',  action='store', nargs='?',  default='ts or ti or te', help='basket 1 condition')
parser.add_argument('-b2c',  action='store', nargs='?',  default='tl or ta', help='basket 2 condition')
parser.add_argument('-ems',  action='store', nargs='?',  default=20, const=0, type=int, help='eject motor speed (for -c em)')
parser.add_argument('-emt',  action='store', nargs='?',  default=100, const=0, type=int, help='eject motor time in milliseconds (for -c em)')
parser.add_argument('-emd',  action='store', nargs='?',  default=0, const=0, type=int, help='eject motor direction (for -c em)')
parser.add_argument('-sms',  action='store', nargs='?',  default=20, const=0, type=int, help='sorter motor speed (for -c sm)')
parser.add_argument('-smt',  action='store', nargs='?',  default=100, const=0, type=int, help='sorter motor time in milliseconds (for -c sm)')
parser.add_argument('-smd',  action='store', nargs='?',  default=0, const=0, type=int, help='sorter motor direction (for -c sm)')


# parser.add_argument('eject')
# parser.add_argument('sort')
#parser.print_help()
# args = parser.parse_args()
# print(args)

#sort_machine()

args = parser.parse_args()
print(args)
if args.c == '':
  print('-c <empty>')
elif args.c == 'all':
  sort_machine();
elif args.c == 'eb':
  for i in range(args.r):
    card_eject();
    card_sort(args.b);
elif args.c == 'em':
  motor_run(eject_motor_adr,args.ems,args.emd)
  time.sleep(args.emt/1000.0)
  motor_break(eject_motor_adr)
elif args.c == 'sm':
  motor_run(sorter_motor_adr,args.sms,args.smd)
  time.sleep(args.smt/1000.0)
  motor_break(sorter_motor_adr)
elif args.c == 'tc':
  card_prop = read_json('mtg_card_prop.json')
  print(args.b0c)
  print(eval_cond(args.b0c, card_prop[0]));
  print(args.b1c)
  print(eval_cond(args.b1c, card_prop[0]));
  print(args.b2c)
  print(eval_cond(args.b2c, card_prop[0]));
  
  