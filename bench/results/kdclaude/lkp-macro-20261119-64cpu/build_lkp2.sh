#!/bin/bash
# build_lkp2.sh [COMPONENT...]: build the additional lkp-tests candidates of
# this round (README section 3) in the guest, from /root/host_fs/lkpbench/src2
# (sources fetched on the cloud host with lkp's PKGBUILD URLs,
# /root/lkpsrc/fetch.sh there) into /root/lkpbench. The first round's
# components are built by ../lkp-macro-20261118-64cpu/build_lkp.sh.
# One log per component in /root/lkpbench/logs; a component that fails is
# reported and left out of the screening, it is not a pass.
# Components: netperf redis libevent memcached memtier sysbench blogbench
# filebench fio pgsql adrestia sockperf (default: all).
S=/root/host_fs/lkpbench/src2; B=/root/lkpbench; L=$B/logs
P=/root/host_fs/lkpbench/lkp-tests/programs
mkdir -p $B $L
J=$(nproc)
copy() { rm -rf $B/$1 && cp -r $S/$1 $B/$1; }
build() {
	( b_$1 ) > $L/$1.log 2>&1
	echo "$1: exit $?"
}
b_netperf() {
	copy netperf; cd $B/netperf && ./autogen.sh && \
		./configure CFLAGS="-O2 -fcommon -std=gnu89 -Wno-error" --enable-demo --disable-sctp && make -j$J
}
b_redis() { copy redis; cd $B/redis && make -j$J MALLOC=libc BUILD_TLS=no; }
b_libevent() {
	rm -rf $B/libevent-2.1.12-stable && tar -xzf $S/libevent-2.1.12-stable.tar.gz -C $B && cd $B/libevent-2.1.12-stable || return 1
	./configure --prefix=$B/libevent --disable-openssl --disable-shared && make -j$J && make install
}
b_memcached() {
	rm -rf $B/memcached-1.6.39 && tar -xzf $S/memcached-1.6.39.tar.gz -C $B && cd $B/memcached-1.6.39 || return 1
	./configure --with-libevent=$B/libevent && make -j$J
}
b_memtier() {
	copy memtier_benchmark; cd $B/memtier_benchmark || return 1
	autoreconf -ivf && PKG_CONFIG_PATH=$B/libevent/lib/pkgconfig ./configure --disable-tls && make -j$J
}
b_sysbench() {
	copy sysbench; cd $B/sysbench || return 1
	patch -p1 < $P/sysbench/pkg/fix-race-in-rnd.patch
	./autogen.sh && ./configure --without-mysql && make -j$J
}
b_blogbench() {
	rm -rf $B/blogbench-1.2 && tar -xzf $S/blogbench-1.2.tar.gz -C $B && cd $B/blogbench-1.2 || return 1
	./configure CFLAGS="-O2 -std=gnu89 -Wno-error" && make -j$J
}
b_filebench() {
	copy filebench; cd $B/filebench || return 1
	patch -p1 < $P/filebench/pkg/filebench01.patch; patch -p1 < $P/filebench/pkg/filebench02.patch
	# As lkp's PKGBUILD: a run command where a workload has none, and no
	# "cached" attribute (filebench dropped it).
	for f in workloads/*.f; do
		grep -q ^run "$f" || printf "\nrun 60\n" >> "$f"
		sed -i '/set \$cached=false/d' $f
		sed -ri 's/(.*),cached=\$cached/\1/g' $f
	done
	libtoolize && aclocal && autoheader && automake --add-missing && autoconf && \
		./configure CFLAGS="-O2 -fcommon -std=gnu89 -Wno-error" --prefix=$B/filebench/inst && make -j$J && make install
}
b_fio() { copy fio; cd $B/fio && ./configure && make -j$J; }
b_pgsql() {
	rm -rf $B/postgresql-17.6 && tar -xjf $S/postgresql-17.6.tar.bz2 -C $B && cd $B/postgresql-17.6 || return 1
	./configure --prefix=/opt/lkp-pgsql --without-readline --without-icu --without-zlib && \
		make -j$J && make install && make -C contrib/pgbench install
}
b_adrestia() { copy adrestia; cd $B/adrestia && make; }
b_sockperf() { copy sockperf; cd $B/sockperf && ./autogen.sh && ./configure && make -j$J; }
for c in ${@:-netperf redis libevent memcached memtier sysbench blogbench filebench fio pgsql adrestia sockperf}; do
	build $c
done
echo BUILD_LKP2_DONE
