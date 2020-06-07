CFLAGS = -g -Wall

SRC = drv8830.c

OBJ = $(SRC:.c=.o)

drv8830: $(OBJ) 
	$(CC) $(CFLAGS) $(LDFLAGS) $(OBJ) -o drv8830 -lwiringPi

clean:	
	-rm $(OBJ) drv8830

