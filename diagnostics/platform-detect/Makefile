GBDK_HOME ?= /opt/gbdk
CC = $(GBDK_HOME)/bin/lcc
CFLAGS = -Wm-yc -Wm-ynPLATDETECT -Wl-m -Wl-j

all: platform-detect.gbc

platform-detect.gbc: src/main.c
	$(CC) $(CFLAGS) -o $@ src/main.c

clean:
	rm -f platform-detect.gbc platform-detect.map platform-detect.noi

.PHONY: all clean
