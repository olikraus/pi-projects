/*
	drv8830.c

	http://wiringpi.com/reference/
	
	gcc -Wall -o drv8830 drv8830.c -lwiringPi
	
	for i in {1..5}; do ./drv8830; done
	

	https://files.seeedstudio.com/wiki/Grove-Mini_I2C_Motor_Driver_v1.0/res/DRV8830.pdf
	
	DRV8830 I2C Addresses of the Grove Mini
		0xc0 --> 0x60
		0xca --> 0x65
		
	DRV8830 Register
		0:	Control, 0: IN1, 1: IN2, 2..7: VSET
		1:	Fault code
		
		
		VSET: 0x06 .. 0x03f
	
		IN1		IN2		OUT1	OUT2	Function
		0		0		Z		Z		Standby/coast
		0		1		L		H		Reverse
		1		0		H		L		Forward
		1		1		H		H		Brake

	load i2c subsystem into the kernel
		gpio load i2c --> does not work instead:
	use raspi-config to enable the i2c subsystem!
		raspi-config
	detect any i2c devices:
		gpio i2cdetect
	
*/

#include <unistd.h>  		// usleep
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include "wiringPi.h"
#include "wiringPiI2C.h"

#define DRV8830_MODE_STANDBY 0
#define DRV8830_MODE_FORWARD 1
#define DRV8830_MODE_REVERSE 2
#define DRV8830_MODE_BREAK 3

struct _drv8830_struct
{
	int fd;			/* file descripter as returned by int wiringPiI2CSetup (int devId) ; */
	uint8_t address;	/* i2c address */
	uint8_t speed;		/* between 0x06 (6) and 0x03f (63)*/
	uint8_t mode;		/* one of the defines above */
};
typedef struct _drv8830_struct drv8830_t;


drv8830_t mot0;
drv8830_t mot1;

/* will call exit(1) if there is any fault condition active */
int drv8830_check_fault_condition(drv8830_t *drv8830, const char *hint)
{
	int val;
	val = wiringPiI2CReadReg8(drv8830->fd, 1);
	if ( (val & 127) != 0 )
	{
		printf("drv8830 %02x %sfault %02x (%s)\n", drv8830->address, (val&1)?"critical ":"", val, hint);
		if ( val & 2 ) printf("drv8830 OCP: Overcurrent event\n");
		if ( val & 4 ) printf("drv8830 UVLO: Undervoltage lockout\n");
		if ( val & 8 ) printf("drv8830 OTS: Overtemperature condition\n");
		if ( val & 16 ) printf("drv8830 ILIMT: Extended current limit event\n");
		/*
		if ( val & 1 )
			exit(1);
		*/
		return 1;		// fault
	}
	return 0; // no fault
}

void drv8830_send_i2c(drv8830_t *drv8830, uint8_t idx, uint8_t val)
{
	static char s[64];
	int err = wiringPiI2CWriteReg8(drv8830->fd, idx, val) ;
	if ( err < 0 )
	{
		sprintf(s, "i2c drv8830 %02x write %02x %02x", drv8830->address, idx, val);
		perror(s);
		exit(1);
	}
}

void drv8830_init(drv8830_t *drv8830, uint8_t address)
{
	static char s[64];
	drv8830->address = address;	
	drv8830->speed = 0x06;
	drv8830->mode = DRV8830_MODE_STANDBY;
	drv8830->fd = wiringPiI2CSetup(address) ;
	if ( drv8830->fd < 0 )
	{
		sprintf(s, "i2c drv8830 %02x init", drv8830->address);
		perror(s);
		exit(1);		
	}
	wiringPiI2CWriteReg8(drv8830->fd, 1, 128) ;  // clear any events
	drv8830_send_i2c(drv8830, 0, (6<<2) | DRV8830_MODE_STANDBY);
	drv8830_check_fault_condition(drv8830, "init");	
}


void drv8830_idle(drv8830_t *drv8830)
{
	drv8830_send_i2c(drv8830, 0, (6<<2) | DRV8830_MODE_STANDBY);
	drv8830_check_fault_condition(drv8830, "idle");	
}

void drv8830_move(drv8830_t *drv8830, uint8_t dir, uint8_t speed)
{
	uint8_t mode;
	if ( dir == 0 )
		mode = DRV8830_MODE_FORWARD;
	else
		mode = DRV8830_MODE_REVERSE;
	if ( speed < 6 )
		speed = 6;
	if ( speed > 0x03f )
		speed = 0x03f;
	drv8830_check_fault_condition(drv8830, "move") ;
	drv8830_send_i2c(drv8830, 0, (speed<<2) | mode);
	wiringPiI2CWriteReg8(drv8830->fd, 1, 128) ;  // clear any events
	//delay(400);
	drv8830_check_fault_condition(drv8830, "move") ;
}


void drv8830_break(drv8830_t *drv8830)
{
	drv8830_send_i2c(drv8830, 0, (6<<2) | DRV8830_MODE_BREAK);
	drv8830_check_fault_condition(drv8830, "break");	
}

void drv8830_ramp(drv8830_t *drv8830, uint8_t dir, int from, int to, int msec)
{
	int start, curr,next, end;
	int offset = 300;
	int speed; 
	start = millis();
	end = start + msec;
	for(;;)
	{
		curr = millis();
		if ( end+offset <= curr )
			break;
		speed = from+ ((to-from)*(curr-start))/(msec);
		printf("start=%d end=%d curr=%d speed=%d\n", start, end, curr, speed);
		drv8830_move(drv8830, dir,  speed);
		next = curr + offset;
		while( next > millis() )
			;
	}
	drv8830_move(drv8830, dir, to);
}


int main(int argc, char **argv)
{
	wiringPiSetup();	// will always return 0
	
	// pinMode (9, OUTPUT) ;
	// digitalWrite (9, HIGH) ; 
/*
	revolutions = k * speed * time
	1/2 = 20 * 615/k		--> k = 24600
        1/2 = 22 * 545/k		--> k = 23980
	1/2 = 30 * 408/k		--> k = 24480
	
*/
	drv8830_init(&mot0, 0x060);
	delay(100);
	drv8830_move(&mot0, 0, 22);
	delay(554);
	if ( drv8830_check_fault_condition(&mot0, "post move")  )
	{
		drv8830_move(&mot0, 1, 60);
		delay(40);
		drv8830_move(&mot0, 0, 60);
		delay(40);
		drv8830_move(&mot0, 1, 60);
		delay(40);
		drv8830_move(&mot0, 0, 60);
		delay(40);
		
	}
	/*
	drv8830_move(&mot0, 0, 40);
	delay(500);
	drv8830_move(&mot0, 0, 50);
	delay(500);
	drv8830_move(&mot0, 0, 40);
	delay(500);
	drv8830_move(&mot0, 0, 30);
	delay(500);
	*/
	//drv8830_idle(&mot0);	
	//drv8830_ramp(&mot0, 0, 40, 50, 5000);
	//drv8830_ramp(&mot0, 0, 20, 6, 1000);
	//drv8830_idle(&mot0);
	drv8830_break(&mot0);	
	delay(500);
	return 0;
}

