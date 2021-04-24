#!/bin/bash

DIR="$(dirname $(readlink -f $0))"
curdir="$(pwd)"
pid="$$"
echo "$pid"

if [ "$1" = "select" ]; then
	fullpath=`echo "$2" | cut -d ";" -f 1`
	filepath=`echo "$2" | cut -d ";" -f 2`
	filename=`echo "$2" | cut -d ";" -f 3`
	echo "$fullpath"
	if [ "$filename" = ".." ]; then
		#tmux send-keys -t "$4" C-e "cd $fullpath" Enter 
		$DIR/filetree.py init "$3" "$fullpath"
	elif [ -d "$fullpath" ]; then
		$DIR/filetree.py toggle "$3" "$fullpath"
	else
		echo "FP: [$fullpath]"
		#tmux send-keys -t "$4" C-e "tab $filepath" Enter \; select-pane -t "$4"
	fi
	exit 0
fi 

if [ "$1" = "home" ]; then
	fullpath=`echo "$2" | cut -d ";" -f 1`
	filepath=`echo "$2" | cut -d ";" -f 2`
	filename=`echo "$2" | cut -d ";" -f 3`
	if [ -d "$filepath" ]; then
		#tmux send-keys -t "$4" C-e "cd $fullpath" Enter 
		$DIR/filetree.py init "$3" "$fullpath"
	fi
	exit 0
fi

if [ "$1" = "display" ]; then
	$DIR/filetree.py init "$pid" "$(pwd)"
	$DIR/filetree.py "print" "$pid" | $DIR/fzf/bin/fzf --layout reverse-list --delimiter ";" --with-nth -1 --ansi \
		--bind "home:execute-silent($DIR/treemenu.sh home {} $pid $2)+reload($DIR/filetree.py 'print' $pid),left-click:execute-silent($DIR/treemenu.sh select {} $pid $2)+reload($DIR/filetree.py 'print' $pid),double-click:execute-silent($DIR/treemenu.sh select {} $pid $2)+reload($DIR/filetree.py 'print' $pid),enter:execute-silent($DIR/treemenu.sh select {} $pid $2)+reload($DIR/filetree.py 'print' $pid),space:execute($DIR/fm.sh menu {} < /dev/tty)+reload($DIR/filetree.py 'print' $pid)"
	$DIR/filetree.py destroy "$pid"
	exit 0
fi
