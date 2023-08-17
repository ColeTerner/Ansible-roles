(
(
sudo fuser -vk /var/lib/dpkg/lock
sudo fuser -vk /var/lib/apt/lists/lock
sudo apt install openssh-server
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
sudo systemctl disable apport.service
sudo systemctl mask apport.service
sudo systemctl stop apt-daily.timer
sudo systemctl disable apt-daily.timer
sudo systemctl disable apt-daily.service
sudo systemctl stop apt-daily-upgrade.timer
sudo systemctl disable apt-daily-upgrade.timer
sudo systemctl disable apt-daily-upgrade.service
sudo mv /etc/apt/sources.list /home/detect/sources.list.bak
sudo apt purge -y update-manager-core
sudo fuser -vk /var/lib/dpkg/lock
sudo fuser -vk /var/lib/apt/lists/lock
)
cd /home/detect/
sudo mv /home/detect/ff451/ff451-repo /var/lib/ff451-repo
sudo mv /etc/apt/sources.list /home/detect/sources.list.bak
cd ff451
sudo cp ff451.list /etc/apt/sources.list.d/
sudo apt update
cd /var/lib/ff451-repo
sudo dpkg -i findface-repo*
sudo dpkg -i findface-data*
(sudo apt update
sudo apt install -y findface-facerouter findface-sf-api findface-video-manager findface-video-worker-cpu etcd memcached
sudo apt install -y findface-extraction-api findface-counter
sudo apt install -y python3-motor ffmpeg
sudo apt install -y findface-ntls
sudo apt install -y curl
sudo apt install -y byobu
sudo apt install -y jq openssh-server htop
sudo apt install -y vim 
sudo apt install -y ntp)
(cd /home/detect/ff451
sudo cp unlift.service /etc/systemd/system/
sudo cp unlift-updater.service /etc/systemd/system/
sudo mkdir -p /opt/unlift/unlift_proxy
sudo mkdir -p /opt/unlift/unlift_updater
sudo cp updater.py /opt/unlift/unlift_updater/updater.py
sudo cp unlift3.py /opt/unlift/unlift_proxy/unlift.py
sudo cp unlift.ini /etc/
sudo cp unlift_updater.ini /etc/unlift-updater.ini
sudo mkdir /etc/unlift_plugins/
sudo cp unlift-plugin.py /etc/unlift_plugins/
sudo chmod 755 /etc/unlift_plugins/unlift-plugin.py
sudo cp findface-extraction-api.ini /etc/findface-extraction-api.ini
cd /home/detect/ff451
sudo cp findface-video-worker-cpu.ini /etc/findface-video-worker-cpu.ini
sudo cp findface-video-manager.conf /etc/findface-video-manager.conf
sudo chown root:ntech /etc/findface-video-manager.conf
sudo cp findface-sf-api.ini /etc/findface-sf-api.ini
sudo cp findface-facerouter.py /etc/findface-facerouter.py
sudo mkdir /opt/unlift/samples
sudo cp sample.mp4 /opt/unlift/samples/
sudo cp /home/detect/ff451/warning.mp3 /opt/unlift/unlift_proxy/
sudo cp /home/detect/ff451/warningf.mp3 /opt/unlift/unlift_proxy/
sudo cp /home/detect/ff451/notice.mp3 /opt/unlift/unlift_proxy/
sudo cp memcached.conf /etc/memcached.conf)
OLD_TOKEN=`cat /home/detect/unlift_token`
sudo sed -i "s/T0KEN/$OLD_TOKEN/g" /etc/unlift.ini
sudo sed -i "s/T0KEN/$OLD_TOKEN/g" /etc/unlift-updater.ini
#CHANGE!!!!
sudo -i sed -i "s/ntls_addr.*/ntls_addr = face452k.bit-tech.co:3136/g" /etc/findface-video-worker-cpu.ini
sudo sed -i "s/license_ntls_server:.*/license_ntls_server: face452k.bit-tech.co:3136/g" /etc/findface-extraction-api.ini
sudo sed -i "s/face: .*/face: face\/kiwi_320.cpu.fnk/g" /etc/findface-extraction-api.ini
sudo sed -i "s/face5/face452k/g" /etc/findface-sf-api.ini
(sudo systemctl enable unlift.service && sudo systemctl start unlift
sudo systemctl enable unlift-updater.service && sudo systemctl start unlift-updater
sudo systemctl enable findface-facerouter.service && sudo systemctl start findface-facerouter.service
sudo systemctl enable findface-extraction-api.service && sudo systemctl start findface-extraction-api.service
sudo systemctl enable findface-sf-api.service && sudo systemctl start findface-sf-api.service
sudo systemctl enable findface-facerouter.service && sudo systemctl start findface-facerouter.service
sudo systemctl enable etcd.service && sudo systemctl start etcd.service
sudo systemctl enable findface-video-manager.service && sudo systemctl start findface-video-manager.service
sudo systemctl enable findface-video-worker-cpu.service && sudo systemctl start findface-video-worker-cpu.service)
sudo sed -i '$a sound=True' /etc/unlift.ini
(sudo sed -i '$a disable_ssl=True' /etc/unlift.ini
sudo sed -i '$a disable_ssl=True' /etc/unlift-updater.ini)
# sudo systemctl enable findface-ntls.service && sudo systemctl start findface-ntls.service
sudo mv /etc/ntp.conf /etc/ntp.conf.bak
echo "server 0.pool.ntp.org" | sudo tee /etc/ntp.conf 
echo "server 1.pool.ntp.org" | sudo tee -a /etc/ntp.conf 
sudo service ntp restart
tim=`echo "$[ ( $RANDOM % 6 )  + 2 ]"`
day=`echo "$[ ( $RANDOM % 28 )  + 1 ]"`
 (sudo crontab -l ; echo "10 $tim * * * sudo service findface-video-worker-cpu restart") | sudo crontab -
#(sudo crontab -l ; echo "0 $tim * * * sudo reboot") | sudo crontab -
(sudo crontab -l ; echo "0 $tim $day * * (sleep 180s;sudo systemctl stop findface-facerouter findface-sf-api findface-video-manager findface-video-worker-cpu etcd findface-extraction-api unlift unlift-updater;sleep 60s;sudo reboot)") | sudo crontab -
(a=`sudo amixer sget Master|grep "%"|cut -d " " -f6|sed -e "s/\[//" -e "s/\]//"`
(sudo crontab -l ;echo "@reboot sudo amixer set Master playback $a;sudo amixer set Master unmute; sudo alsactl store")|sudo crontab -)
a=$(cat /proc/cpuinfo | grep "cpu cores" | tail -n 1|cut -d ":" -f2)
if (($a >4))
then sudo sed -i 's/batch_size = .*/batch_size = 6/' /etc/findface-video-worker-*pu.ini
else sudo sed -i 's/batch_size = .*/batch_size = 4/' /etc/findface-video-worker-*pu.ini
fi
(sudo sed -i "s/currentversion =.*/currentversion = 1/" /etc/unlift-updater.ini 
sudo systemctl restart unlift-updater.service )
)
