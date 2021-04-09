

from picamera import PiCamera
from picamera.array import PiRGBArray
import numpy as np
import cv2
import os

import smbus
import time


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
	motor_shake(3, 0.04, 0.03)
	motor_shake(20, 0.05, 0.04)

	# throw out lowest card
	motor_run(eject_adr, 30, 0)
	time.sleep(0.35)
	motor_coast(eject_adr)
	time.sleep(0.1)


	# pull back second lowest card
	motor_run(eject_adr, 30, 1)

	# in parallel shake card in the sorter and pull back the second lowest card
	for i in range(10):
		motor_run(sorter_adr, 30, 0)
		time.sleep(0.04)
		motor_break(sorter_adr)
		time.sleep(0.01)
		motor_run(sorter_adr, 30, 1)
		time.sleep(0.04)
		motor_break(sorter_adr)
		time.sleep(0.01)
	
	# stop pullback
	motor_coast(eject_adr)
	time.sleep(0.1)

def card_sort():
	motor_run(sorter_adr, 30, 1)
	time.sleep(1)
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

def cam_capture(cam, imagename):
	rawCapture = PiRGBArray(cam)
	#camera.capture('image.jpg')
	cam.capture(rawCapture, format="bgr")
	#image = remove_barrel_distortion(white_balance(rawCapture.array))
	image = remove_barrel_distortion(rawCapture.array)
	#image = rawCapture.array;
	image = image[0:150, 0:1279]
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


for i in range(30):
	card_eject()
	time.sleep(0.4)

	t = time.time()
	cam_capture(camera, 'image_' + str(t) +'.jpg')
	#os.system('tesseract --dpi 500 --psm 6 image.jpg out txt')  # write to out.txt
	#t = read_file('out.txt')
	#print(t)
	card_sort()

#light.off();
camera.stop_preview()
