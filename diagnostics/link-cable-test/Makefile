GBDK_HOME ?= /opt/gbdk
CC = $(GBDK_HOME)/bin/lcc
CFLAGS = -Wm-yC -Wm-ynLINKSUSTAIN -Wl-m -Wl-j

all: link-sustain.gbc

link-sustain.gbc: src/main.c src/protocol.c src/protocol.h
	$(CC) $(CFLAGS) -o $@ src/main.c src/protocol.c

clean:
	rm -f link-sustain.gbc link-sustain.map link-sustain.noi

.PHONY: all clean
