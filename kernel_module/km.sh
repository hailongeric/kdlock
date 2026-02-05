#!/bin/sh

if [ -n "$1" ]
then
  TP="$1"
fi

if [ -n "$3" ]
then
  wnum="$3"
fi

insed=`lsmod | sed -n '/kdlock_km/p'`
if [ ! -n "$insed" ]; then
	echo ""
else
	sudo rmmod kdlock_km
fi

if [ ! -n "$2" ]
then
	sudo insmod ./kdlock_km.ko target_process=\"$TP\"
elif [ $2 = "UB" ]
then
	sudo insmod ./kdlock_km.ko target_process=\"$TP\" velvet_wait_queue=0 delegate_election=0
elif [ $2 = "DE" ]
then
	sudo insmod ./kdlock_km.ko target_process=\"$TP\" velvet_wait_queue=0
elif [ $2 = "VW" ]
then
	sudo insmod ./kdlock_km.ko target_process=\"$TP\" delegate_election=0
fi