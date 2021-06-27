

from picamera import PiCamera
from picamera.array import PiRGBArray
import numpy as np
import cv2
import os
import io
import json
import jellyfish

import smbus
import time
import argparse

#pytesseract.pytesseract.tesseract_cmd = r'/usr/bin/tesseract'

# DRV8830
#	Register 0: 	vvvvvvbb
#	Register 1:	c--4321f
#
#	bb = 00		coast
#	bb = 01		reverse
#	bb = 10		forward
#	bb = 11		break
# around one second is required to reach full speed (from 0 to 63)


eject_adr = 0x65
sorter_adr = 0x60

b0cond = "true";
b1cond = "true";
b2cond = "true";
# b0cond = "true";


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
	
def motor_shake(cnt, d1, d2):
	for i in range(cnt):
		motor_run(eject_adr, 30, 0)
		time.sleep(d1)
		motor_break(eject_adr)
		time.sleep(0.01)
		motor_run(eject_adr, 30, 1)
		time.sleep(d2)
		motor_break(eject_adr)
		time.sleep(0.01)

def card_eject():
	# try to separate lowest card
	motor_shake(5, 0.04, 0.03)
	motor_shake(20, 0.05, 0.04)

	# throw out lowest card
	motor_run(eject_adr, 30, 0)
	time.sleep(0.30)
	motor_coast(eject_adr)
	time.sleep(0.1)


	# pull back second lowest card
	motor_run(eject_adr, 25, 1)

	# in parallel shake card in the sorter and pull back the second lowest card
	for i in range(6):
		motor_run(sorter_adr, 15, 0)
		time.sleep(0.025)
		motor_break(sorter_adr)
		time.sleep(0.01)
		motor_run(sorter_adr, 15, 1)
		time.sleep(0.025)
		motor_break(sorter_adr)
		time.sleep(0.01)
	
        # continue with pullback
	time.sleep(1)
	# stop pullback
	motor_coast(eject_adr)
	time.sleep(0.1)

def card_sort(basket):
  if (basket & 2) == 0:
    motor_run(sorter_adr, 21, 1)
    time.sleep(1.2)
  else:
    #motor_run(sorter_adr, 30, 1)
    #time.sleep(0.15)
    #motor_run(sorter_adr, 40, 1)
    #time.sleep(0.15)
    #motor_run(sorter_adr, 50, 1)
    #time.sleep(0.15)
    motor_run(sorter_adr, 63, 1)
    time.sleep(1.2)
  motor_coast(sorter_adr)
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

	# TODO: add your coefficients here!
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

def cam_capture(cam, imagename):
	rawCapture = PiRGBArray(cam)
	#camera.capture('image.jpg')
	cam.capture(rawCapture, format="bgr")
	#image = remove_barrel_distortion(white_balance(rawCapture.array))
	image = remove_barrel_distortion(rawCapture.array)
	#image = rawCapture.array;
	image = image[0:135, 0:1279]
	#image2 = image[0:100, 0:639]

	# https://stackoverflow.com/questions/9480013/image-processing-to-improve-tesseract-ocr-accuracy
	image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
	#(thresh, blackAndWhiteImage) = cv2.threshold(image, 120, 255, cv2.THRESH_BINARY)

	kernel = np.ones((3, 3), np.uint8)
	img = cv2.dilate(image, kernel, iterations=1)
	img = cv2.erode(img, kernel, iterations=1)	
	img = cv2.adaptiveThreshold(cv2.medianBlur(img, 3), 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 63, 2)
	
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
  dmin = 999   # minimal distance for smin
  smin = ""     # the best matching card name (with minimal distance)
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
  # [carddic[smin], smin, dmin]
  # return the internal card index into the property array
  return carddic[smin]

def get_sort_basket(cardprop, card_idx)
  basket = 3;
  r = cardprop[card_idx]["r"];          # rarity, 0="Common", 1="Uncommon", 2="Rare", 3="Mythic"
  tc = cardprop[card_idx]["tc"];        # is Creature?
  ts = cardprop[card_idx]["ts"];        # is Sorcery?
  ti = cardprop[card_idx]["ti"];        # is Instant?
  ta = cardprop[card_idx]["ta"];        # is Artefact?
  tl = cardprop[card_idx]["tl"];        # is Land?
  te = cardprop[card_idx]["te"];        # is Enhancement?
  tp = cardprop[card_idx]["te"];        # is Planeswalker?
  m = cardprop[card_idx]["m"];        # cmc 
  if eval(b0cond):
    basket = 0
  elif eval(b1cond):
    basket = 1
  elif eval(b2cond):
    basket = 2
  return basket;

def sort_machine():
  card_dic = read_json('mtg_card_dic.json')
  card_prop = read_json('mtg_card_prop_full.json')


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
    cam_capture(camera, 'image.jpg')
    t_cam = time.time()
    ocr_name = get_ocr_card_name('image.jpg')
    t_ocr = time.time()
    card_idx = find_card(card_dic, ocr_name)
    t_find = time.time()
    basket = get_sort_basket(card_prop, card_idx)
    
    card_sort(0)
    append_to_file("drv_and_cam.log", "cam: "+str(t_cam-t)+', ocr: '+str(t_ocr - t_cam)+', find: '+str(t_find-t_ocr)  )
  #light.off();
  camera.stop_preview()

parser = argparse.ArgumentParser(description='Card Sorter Machine Controller',
  formatter_class=argparse.RawTextHelpFormatter)
parser.add_argument('-c',
                    default='all',
                    const='all',
                    nargs='?',
                    choices=['eject', 'sort', 'all'],
                    help='''Define command to execute (default: %(default)s)
    eject: Eject a card into sorter
    sort: Move a cart from the sorter into a basket
''')
parser.add_argument('-b', 
  action='store',
  nargs='?', 
  default=0,
  const=0,
  type=int,
  help='target basket number')
parser.add_argument('-r', 
  action='store',
  nargs='?', 
  default=1,
  const=1,
  type=int,
  help='repeat count')
parser.add_argument('-b0c', 
  action='store',
  nargs='?', 
  default='true',
  const=1,
  type=string,
  help='sort condition for basket 0')
parser.add_argument('-b1c', 
  action='store',
  nargs='?', 
  default='true',
  const=1,
  type=string,
  help='sort condition for basket 0')
parser.add_argument('-b2c', 
  action='store',
  nargs='?', 
  default='true',
  const=1,
  type=string,
  help='sort condition for basket 0')

# parser.add_argument('eject')
# parser.add_argument('sort')
#parser.print_help()
# args = parser.parse_args()
# print(args)

#sort_machine()

args = parser.parse_args()
print(args)
b0cod = args.b0c
b1cod = args.b1c
b2cod = args.b2c

if args.c == '':
  print('-c <empty>')
elif args.c == 'all':
  print('-c all')
elif args.c == 'eject':
  for i in range(args.r):
    card_eject();
    card_sort(args.b);

