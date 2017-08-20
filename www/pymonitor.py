import os, sys, time, subprocess

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

def log(s):
	print('[Monitor] %s' %s )

class MyFileSystemEventHandler(FileSystemEventHandler):
	def __init__(self,fn):
		super(MyFileSystemEventHandler,self).__init__()
		self.restart = fn
	#当.py文件发生变化时自动记录并重启
	def on_any_event(self,event):
		if event.src_path.endswith('.py'):
			log('Python source file changed: %s' % event.src_path)
			self.restart()

command = ['echo', 'ok']
process = None

def start_process():
	global process,command
	log('Start process %s...' % ' '.join(command))
	 # 利用Python自带的subprocess实现进程的启动和终止，并把输入输出重定向到当前进程的输入输出中
	process = subprocess.Popen(command, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr)


def kill_process():
	global process
	if process:
		log('Kill process [%s]...' % process.pid)
		process.kill()
		process.wait()
		log('Process ended with code %s.' % process.returncode)
		process = None

def restart_process():
	kill_process()
	start_process()

#监控程序
def start_watch(path,callback):
	observer = Observer()
	#指定监控路径和触发事件调用的方法
	observer.schedule(MyFileSystemEventHandler(restart_process),path,recursive=True)
	observer.start()
	log('Watching directory %s...' % path)
	start_process()
	try:
		while True:
			time.sleep(0.5)
	except KeyboardInterrupt:
		observer.stop()
	observer.join()

if __name__ == '__main__':
	argv = sys.argv[1:]#argr是传入的参数的列表，第一个参数是self
	if not argv:
		print('Usage: ./pymonitor app.py')
		exit(0)
	if argv[0] != 'python':
		argv.insert(0,'python')
	command = argv
	path = os.path.abspath('.')#返回当前运行文件的绝对路径，在该项目即www文件夹路径
	start_watch(path,None)
