#!/bin/bash
# build_lkp.sh [COMPONENT...]: build the lkp-tests candidates in the guest
# from /root/host_fs/lkpbench (sources fetched on 380G10, README 4.1) into
# /root/lkpbench, with lkp's own build steps (programs/*/pkg/PKGBUILD).
# One log per component in /root/lkpbench/logs.
# Components: wis stressng vmscal hackbench unixbench pft schbench fsmark
# dbench ebizzy aim7 reaim tlbflush (default: all).
S=/root/host_fs/lkpbench; B=/root/lkpbench; L=$B/logs
P=$S/lkp-tests/programs
mkdir -p $B $L
J=$(nproc)
copy() { rm -rf $B/$1 && cp -r $S/$1 $B/$1; }
build() {
	( b_$1 ) > $L/$1.log 2>&1
	echo "$1: exit $?"
}
b_wis() { copy wis-upstream 2>/dev/null || cp -r /root/host_fs/appbench/wis-upstream $B/wis-upstream; cd $B/wis-upstream && make -j$J; }
b_stressng() { copy stress-ng; cd $B/stress-ng && make -j$J; }
b_vmscal() { copy vm-scalability; cd $B/vm-scalability && make -j$J; }
b_hackbench() { copy rt-tests; cd $B/rt-tests && make hackbench; }
b_unixbench() { copy byte-unixbench; cd $B/byte-unixbench/UnixBench && make -j$J; }
b_pft() { copy pft; cd $B/pft && make; }
b_schbench() { copy schbench; cd $B/schbench && make; }
b_fsmark() { copy fs_mark; cd $B/fs_mark && make; }
b_dbench() { copy dbench; cd $B/dbench && ./autogen.sh && ./configure && make -j$J; }
b_ebizzy() {
	rm -rf $B/ebizzy-0.3 && tar -xzf $S/ebizzy-0.3.tar.gz -C $B && cd $B/ebizzy-0.3 || return 1
	patch -p1 < $P/ebizzy/pkg/0001-ebizzy.patch && ./configure && make
}
b_aim7() {
	rm -rf $B/aim7 && mkdir -p $B/aim7 && cd $B/aim7 && tar -xzf $S/s7110.tar.Z || return 1
	cd s7110 2>/dev/null || cd $(ls -d */ | head -1)
	patch -p1 < $P/aim7/pkg/01.patch
	printf '\n\n1\ngcc\n-O2 -Wno-error=implicit-int -std=gnu89\n\n\nn\n' | make
	make
}
b_reaim() {
	rm -rf $B/osdl-aim-7 && tar -xzf $S/osdl-aim-7.0.1.13.tar.gz -C $B && cd $B/osdl-aim-7 || return 1
	patch -p1 < $P/reaim/pkg/reaim.patch
	./bootstrap && LDFLAGS=-laio ./configure && \
		make CFLAGS="-Wno-implicit-int -Wno-int-conversion -fcommon -I$B/osdl-aim-7/include -D_GNU_SOURCE -lm"
}
b_tlbflush() {
	mkdir -p $B/tlbflush && cd $B/tlbflush && \
		gcc -DFILE_SIZE=$((128*1048576)) -g -O2 $P/tlbflush/pkg/tlbflush.c -lpthread -o tlbflush
}
for c in ${@:-wis stressng vmscal hackbench unixbench pft schbench fsmark dbench ebizzy aim7 reaim tlbflush}; do
	build $c
done
echo BUILD_LKP_DONE
