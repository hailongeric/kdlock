#!/bin/bash
# prep_text.sh: the Psearchy input, a copy of the kernel source tree of the
# kdall/kdnat builds (/mnt/kdlock-builds/kda/src, no build output there),
# and its file list, largest first (psearchy/mkfiles).
A=/root/appbench
rm -rf $A/text && mkdir -p $A/text
rsync -a --exclude .git /mnt/kdlock-builds/kda/src/ $A/text/linux/
$A/ivm/psearchy/mkfiles $A/text/linux > $A/text-files.txt
echo "files $(wc -l < $A/text-files.txt) size $(du -sh $A/text | cut -f1)"
