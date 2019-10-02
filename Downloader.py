import socket,select,re,ssl,threading,sys,os
from urllib.parse import urlparse
from time import sleep

global temp1
temp1=0
def run():
	global temp1
	while when:
		speed=(gg-temp1)/1024
		p=int(int(gg)*50/int(size))
		print("Process: [{}] {}% Complete {:<8}Kb/s".format("█"*p+"-"*(50-p), p*100/50,"{:.2f}".format(speed)),end="\r")
		temp1=gg
		sleep(1)
def hparsec(data):
	headers =  data.split(b'\r\n\r\n')[0]
	html = data[len(headers)+4:]
	headers=headers.decode().split("\r\n")
	out={}
	out["status"]=headers[0].split()[1]
	for n in headers[1:]:
		temp=n.split(":")
		value=""
		for n in temp[1:]:
			value+=n+":"
		out[temp[0].lower()]=value[1:len(value)-1]
	return out
def main(urlinit=""):
	if not urlinit:
		urlinit=input("Download Link -->")
		#urlinit="http://www.panacherock.com/downloads/mp3/01_Sayso.mp3"
	o=urlparse(urlinit)
	if o.query:
		url=(o.path+"?"+o.query)
		filename=input("Enter Filename -->")
	else:
		url=o.path
		filename=o.path.split("/")[-1]
	host=o.netloc
	send='GET {} HTTP/1.1\r\nHOST:{}\r\nConnection: close\r\nUser-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0 Safari/605.1.15\r\nAccept: */*\r\n\r\n'.format(url,host)
	s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	if o.scheme=="https":
		s.connect((host, 443))
		s = ssl.create_default_context().wrap_socket(s, server_hostname=host)
	elif o.scheme=="http":
		s.connect((host, 80))
	else:
		print("we only support HTTP and HTTPS")
	s.sendall(send.encode("ascii"))
	data = s.recv(1024)
	headers =  data.split(b'\r\n\r\n')[0]
	image = data[len(headers)+4:]
	headers=hparsec(headers)
	#print((headers["status"]))
	if int(headers["status"]) is not 200:
		s.close()
		main(headers["location"])
	else:
		print("Downloading From: "+host)
	f = open(filename, 'wb')
	f.write(image)
	global size
	print(headers["content-length"])
	try:
		size=headers["content-length"]
		print("Total Size {:.3f} MB".format(int(size)/1048576))
	except:
		print("No size")
	global gg
	gg=len(image)
	global when

	when=True
	threading.Thread(target=run).start()
	while True:
	    data = s.recv(5120)
	    if not data: break
	    f.write(data)
	    gg+=len(data)
	when=False
	p=int(int(gg)*50/int(size))
	print("Process: [{}] {}% Complete {:<10}".format("█"*p+"-"*(50-p), p*100/50,"0.0 Kb/s"))
	f.close()
	print("\nDownloading Completed Filename:{}\n".format(filename))
	os.system("pause")
if __name__ == '__main__':
	main()