#!/bin/bash
# build_apps.sh [COMPONENT...]: build the application benchmarks in the
# guest from /root/appbench (copied from /root/host_fs/appbench). One log
# per component in /root/appbench/logs. Components: wis fxmark leveldb
# metis psearchy wrk httpd (default: all).
A=/root/appbench; L=$A/logs; mkdir -p $L
J=$(nproc)
build() {	# build NAME: run b_NAME, report
	local n=$1
	( b_$n ) > $L/$n.log 2>&1
	echo "$n: exit $?"
}
b_wis() { cd $A/tclocks/will-it-scale && make -j$J; }
b_fxmark() { cd $A/tclocks/fxmark && make -j$J; }
b_leveldb() {
	# db_bench does not link jemalloc, and the copy lacks its doc templates.
	cd $A/tclocks/leveldb-1.20 || return 1
	./build_detect_platform build_config.mk . && make -j$J out-static/db_bench
}
b_metis() { make -C $A/ivm/metis -j$J; }
# Only the indexer (pedsort); the query tool needs Berkeley DB.
b_psearchy() { make -C $A/ivm/psearchy mkdb; }
b_wrk() { make -C $A/wrk -j$J; }
b_httpd() {
	cd $A/ivm/apache || return 1
	rm -rf httpd-2.4.62 apr-1.7.5 apr-util-1.6.3
	tar -xf httpd-2.4.62.tar && tar -xf apr-1.7.5.tar && tar -xf apr-util-1.6.3.tar || return 1
	mv apr-1.7.5 httpd-2.4.62/srclib/apr && mv apr-util-1.6.3 httpd-2.4.62/srclib/apr-util
	cd httpd-2.4.62 && ./configure --with-included-apr --prefix=/usr/local/apache2 && make -j$J && make install
}
for c in ${@:-wis fxmark leveldb metis psearchy wrk httpd}; do build $c; done
echo BUILD_APPS_DONE
