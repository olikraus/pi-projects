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
		--> should detect 0x60 and 0x65
	
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
	delay(10);
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
	//drv8830_check_fault_condition(drv8830, "move") ;
	drv8830_send_i2c(drv8830, 0, (speed<<2) | mode);
	wiringPiI2CWriteReg8(drv8830->fd, 1, 128) ;  // clear any events
	//drv8830_check_fault_condition(drv8830, "move") ;
}


void drv8830_break(drv8830_t *drv8830)
{
	drv8830_send_i2c(drv8830, 0, (6<<2) | DRV8830_MODE_BREAK);
	drv8830_check_fault_condition(drv8830, "break");	
}

/*

	Prototype:
		int drv8830_rotate(drv8830_t *drv8830, uint8_t dir, int speed, int time)
	Description:
		Rotate with speed by time
	Args:
		drv8830: pointer to the drv8830 struct
		dir: 0 or 1
		speed: value between 0x06 and 0x3f. Minium speed seems to be 0x0f
		time: time in milliseconds
*/
int drv8830_rotate(drv8830_t *drv8830, uint8_t dir, int speed, int time)
{
	//int min_time = 350;
	int min_time = 100;
	
	if ( speed < 15 )
	{
		printf("speed too small: increase speed! time=%d, speed=%d\n", time, speed);
		return 0;
	}		
	
	if ( time < min_time )
	{
		printf("time too small: reduce speed! time=%d, speed=%d\n", time, speed);
		return 0;
	}
	
	printf("time=%d, speed=%d\n", time, speed);
	for(;;)
	{
		drv8830_move(&mot0, dir, speed);
		delay(min_time);
		if ( drv8830_check_fault_condition(&mot0, "post move")  )
		{
			drv8830_move(&mot0, 1-dir, 60);
			delay(30);
		}
		else
		{
			if ( time > min_time )
			{
				delay(time-min_time);
			}
			break;
		}
	}
	drv8830_break(&mot0);	
	return 1;
}


/*

	Prototype:
		int drv8830_rotate(drv8830_t *drv8830, uint8_t dir, int speed, int degree)
	Description:
		Rotate by a specific amount of degree
	Args:
		drv8830: pointer to the drv8830 struct
		dir: 0 or 1
		speed: value between 0x06 and 0x3f. Minium speed seems to be 0x0f
		degree: angular value in degree, one full rotation: 360
*/
int drv8830_rotate2(drv8830_t *drv8830, uint8_t dir, int speed, int degree)
{
	/*
		yellow dc motor
	
		The k factor is derived by several experiments.
		It is optimized for speed=20.
		k should be higher for speed < 20 and should be smaller for speed > 20;
	
		speed=15 --> k=84
		speed=34 --> k=69
	        slope = -28/(50-15) = -28/35
	
	*/
	/*
		Do a little bit of k factor compensation so that the degree value
		is more or less ok between speed 15 and 30
		Looks like this value also depends on the engine temperature.
	*/
	
	int k = 84 - ((speed-15)*28)/35;
	//int k = 84;
	//int min_time = 350;
	int min_time = 350;
	int time = degree*k/speed;
	
	if ( speed < 15 )
	{
		printf("speed too small: increase speed! time=%d, speed=%d, r=%d\n", time, speed, degree);
		return 0;
	}		
	
	if ( time < min_time )
	{
		printf("time too small: reduce speed! time=%d, speed=%d, r=%d\n", time, speed, degree);
		return 0;
	}
	
	printf("time=%d, speed=%d, degree=%d, k=%d\n", time, speed, degree, k);
	for(;;)
	{
		drv8830_move(&mot0, dir, speed);
		delay(min_time);
		if ( drv8830_check_fault_condition(&mot0, "post move")  )
		{
			/* fault detected */
			drv8830_move(&mot0, 1-dir, 60);
			delay(30);
		}
		else
		{
			delay(time-min_time);
			break;
		}
	}
	drv8830_break(&mot0);	
	return 1;
}

int main(int argc, char **argv)
{
	int i;
	wiringPiSetup();	// will always return 0
	
	// pinMode (9, OUTPUT) ;
	// digitalWrite (9, HIGH) ; 
	
	drv8830_init(&mot0, 0x060);	
	//drv8830_rotate(&mot0, 0, 20, 180);

	for( i = 0; i < 5; i++ )
	{
		drv8830_rotate(&mot0, 0, 30, 110);
		drv8830_rotate(&mot0, 1, 30, 100);
	}
	delay(200);
	
	drv8830_rotate(&mot0, 0, 15, 530);
	delay(200);
	drv8830_rotate(&mot0, 1, 15, 580);
	
	delay(200);
	return 0;
}

