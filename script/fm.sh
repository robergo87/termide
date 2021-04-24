Skip to content
Search or jump to…

Pull requests
Issues
Marketplace
Explore
 
@robergo87 
robergo87
/
rgsh
1
00
Code
Issues
Pull requests
Actions
Projects
Wiki
Security
Insights
Settings
rgsh/fm.sh
@robergo87
robergo87 tree menu update
Latest commit 44abacd on 11 Aug 2020
 History
 1 contributor
Executable File  72 lines (63 sloc)  1.27 KB
 
#!/bin/bash

clear
DIR="$(dirname $(readlink -f $0))"


if [ "$1" = "menu" ]; then
	filepath=`echo "$2" | cut -d";" -f1`
	opt=`printf "mv\nchmod\ntouch\nmkdir\nrm" | $DIR/fzf/bin/fzf --reverse`
	$DIR/fm.sh "$opt" "$filepath"
	exit 0
fi

if [ "$1" = "touch" ]; then
	echo "new filename"
	read -i "$2" -e filename
	if [ ! -z "$filename" ]; then
		touch "$filename"
	fi
fi

if [ "$1" = "mkdir" ]; then
	echo "new dirname"
	read -i "$2" -e filename
	if [ ! -z "$filename" ]; then
		mkdir "$filename"
	fi
fi

if [ "$1" = "rm" ]; then
	if [ -d "$2" ]; then
		echo "Are you sure you want to delete directory $2 and all of its contents? [y/N]"
		read prompt
		if [ "$prompt" == "y" ]; then
			rm -rf "$2"
		fi
	else
		echo "Are you sure you want to delete file $2? [y/N]"
		read prompt
		if [ "$prompt" == "y" ]; then
			rm "$2"
		fi
	fi
fi

if [ "$1" = "mv" ]; then
	echo "Move $2 to:"
	read -i "$2" -e filename
	if [ ! -z "$filename" ]; then
		mv "$2" "$filename"
	else
		echo "Aborting"
	fi
fi

if [ "$1" = "cp" ]; then
	echo "Move $2 to:"
	read -i "$2" -e filename
	if [ ! -z "$filename" ]; then
		cp -av "$2" "$filename"
	else
		echo "Aborting"
	fi
fi

if [ "$1" = "chmod" ]; then
	echo "Change permissions to $2 to:"
	read -i "755" -e filemod
	if [ ! -z "$filemod" ]; then
		chmod "$filemod" $2
	fi
fi
