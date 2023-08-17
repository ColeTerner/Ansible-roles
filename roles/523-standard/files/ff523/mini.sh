if [ -z "$2" ] 
then x=22;y=$1
else x=$1;y=$2
fi
echo "$x;$y"
rsync -rv --checksum --partial --progress -e "ssh -p $x" --files-from=list ./ $y:~/ff451/
