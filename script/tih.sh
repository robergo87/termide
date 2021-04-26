#!/bin/bash

DIR="$(dirname $(readlink -f $0))"
PDIR="$(dirname $DIR)" 
echo $PDIR

if [ "$1" = "install" ]; then
	cd "$PDIR/micro"
	curl https://getmic.ro | bash
	cd "$PDIR/fzf"
	git clone --depth 1 https://github.com/junegunn/fzf.git
	$PDIR/fzf/fzf/install --no-key-bindings --no-update-rc --no-completion --no-bash
fi

if [ "$1" = "fzf" ]; then
	shift
	$PDIR/fzf/fzf/bin/fzf "$@"
fi

if [ "$1" = "gitadd" ]; then
	toadd=`git status -s | $PDIR/fzf/fzf/bin/fzf -m`
	IFS=$'\n'
	for file in $toadd
	do
		pathonly=`echo "$file" | cut -c 4-`
		echo "git add $pathonly"
		git add "$pathonly"
	done
fi

if [ "$1" = "gitclear" ]; then
	git reset HEAD -- .
fi

if [ "$1" = "vim" ]; then
	shift
	vim -S "$DIR/vim.so" "$@"
fi

if [ "$1" = "micro" ]; then
	shift
	export TERM=xterm-256color
	micro --config-dir "$PDIR/conf/.micro" "$@"
fi

if [ "$1" = "nano" ]; then
	shift
	nano --tabsize=4 -i -S -l -m -T 4 -F "$@"
fi

if [ "$1" = "history" ]; then
	line=`cat ~/.bash_history | tih fzf --layout reverse-list --exact`
	echo "$line"
	echo "$($line)"
fi

if [ "$1" = "popup" ]; then
	shift
	$PDIR/popup "$@"
fi

if [ "$1" = "fm" ]; then
	action=`$PDIR/includes/fm.py actions | $PDIR/fzf/fzf/bin/fzf \
	    --layout reverse-list --delimiter ";" --with-nth -1 --ansi`
	$PDIR/includes/fm.py "$action" "$2"
fi

curdir="$(pwd)"
pid="$$"

if [ "$1" = "tree" ]; then
    python3 $PDIR/includes/tree.py "$pid" init . \
    "termide term_add '$2' '{file}' '[\"$PDIR/script/tih\", \"micro\", \"{path}\"]'; termide tab '$2'" \
    "$PDIR/script/tih popup '{path}' . '$PDIR/script/tih' fm '{path}'" &
    sleep 1
    python3 $PDIR/includes/tree.py "$pid" list | $PDIR/fzf/fzf/bin/fzf  --layout reverse-list --delimiter ";" --with-nth -1 --ansi \
    --bind "enter:reload(python3 $PDIR/includes/tree.py "$pid" select {}),space:reload(python3 $PDIR/includes/tree.py "$pid" alternative {})"
    python3 $PDIR/includes/tree.py "$pid" stop
fi
