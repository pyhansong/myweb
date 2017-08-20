import functools,inspect,asyncio,logging,os
from urllib import parse
from aiohttp import web 
from apis import APIError

#把一个函数映射成一个处理URL函数，编写@get@post，通过装饰器可以让URL处理函数带有URL信息
def get(path):
	def decorator(func):
		@functools.wraps(func)
		def wrapper(*args,**kw):
			return func(*args,**kw)
		wrapper.__method__ = 'GET'
		wrapper.__route__ = path
		return wrapper
	return decorator

def post(path):
	def decorator(func):
		@functools.wraps(func)
		def wrapper(*args,**kw):
			return func(*args,**kw)
		wrapper.__method__ = 'POST'
		wrapper.__route__ = path
		return wrapper
	return decorator

#获取函数的必须要赋值的KEYWORD_ONLY参数
def get_required_kw_args(fn):
	args = []
	params = inspect.signature(fn).parameters#返回这个函数的参数名和参数信息，dict形式
	for name,param in params.items():#以列表返回可遍历的(键, 值) 元组数组
		if param.kind == inspect.Parameter.KEYWORD_ONLY and param.default == inspect.Parameter.empty:#如果参数是一个关键字传入参数且没有默认值
			args.append(name)
	return tuple(args)

#获取所有KEYWORD_ONLY参数
def get_named_kw_args(fn):
	args = []
	params = inspect.signature(fn).parameters
	for name,param in params.items():
		if param.kind == inspect.Parameter.KEYWORD_ONLY:
			args.append(name)
	return tuple(args)
	
	
#监测函数是否有KEYWORD_ONLY参数
def has_named_kw_args(fn):
	params = inspect.signature(fn).parameters
	for name,param in params.items():
		if param.kind == inspect.Parameter.KEYWORD_ONLY:
			return True

#监测函数是否有VAR_KEYWORD参数
def has_var_kw_arg(fn):
	params = inspect.signature(fn).parameters
	for name,param in params.items():
		if param.kind == inspect.Parameter.VAR_KEYWORD:
			return True
			
#是否有request参数，且是否在最后一个参数位置
def has_request_arg(fn):
	sig = inspect.signature(fn)
	params = sig.parameters
	found = False
	for name,param in params.items():
		if name == 'request':
			found = True#找到了request参数
			continue
		if found  and (param.kind != inspect.Parameter.KEYWORD_ONLY and  param.kind!=inspect.Parameter.VAR_KEYWORD and param.kind!=inspect.Parameter.VAR_POSITIONAL):
			raise ValueError('request parameter must be the last named parameter in function: %s%s' % (fn.__name__, str(sig))) 
	return found

#RequestHandler目的就是从URL函数中分析其需要接收的参数，从request中获取必要的参数
class RequestHandler(object):
	def __init__(self, app, fn):
		self._app = app#一个下划线开头声明是私有变量，但是可以外部调用
		self._func = fn
		self._has_request_arg = has_request_arg(fn)
		self._has_var_kw_arg = has_var_kw_arg(fn)
		self._has_named_kw_args = has_named_kw_args(fn)
		self._named_kw_args = get_named_kw_args(fn)
		self._required_kw_args = get_required_kw_args(fn)
	
	# __call__方法的代码逻辑:
	# 1.定义kw对象，用于保存参数
	# 2.判断request对象是否存在参数，如果存在则根据是POST还是GET方法将参数内容保存到kw
	# 3.如果kw为空(说明request没有传递参数)，则将match_info列表里面的资源映射表赋值给kw；如果不为空则把命名关键字参数的内容给kw
	# 4.完善_has_request_arg和_required_kw_args属性
	@asyncio.coroutine
	def __call__(self,request):#__call__方法能够实现实例的直接调用
		kw = None
		if self._has_var_kw_arg or self._has_named_kw_args or self._required_kw_args:
			if request.method == 'POST':
				if not request.content_type:#请求中没有内容类型报错
					return web.HTTPBadRequest(text='Missing Content_Type.')
				ct = request.content_type.lower()
				if ct.startswith('application/json'):#检查content-type形式，给出对应处理request方法
					params = yield from request.json()
					if not isinstance(params,dict):#??json是一个dict类型？？
						return web.HTTPBadRequest(text='JSON body must be object.')
					kw = params #保存请求参数
				elif ct.startswith('application/x-www-form-urlencoded') or ct.startswith('multipart/form-data'):
					params = yield from request.post()
					kw = dict(**params)
				else:
					return web.HTTPBadRequest('Unsupported Content-Type: %s' % request.content_type)
			if request.method == 'GET': # get方法比较简单，直接后面跟了string来请求服务器上的资源
				qs = request.query_string
				if qs:
					# 该方法解析url中?后面的键值对内容保存到kw
					kw = dict()
					for k,v in parse.parse_qs(qs,True).items():#The dictionary keys are the unique variable names and the values are lists of values for each name.
						kw[k] = v[0]#？？为什么每个k都赋值成V[0]
		if kw is None:# 参数为空说明没有从Request对象中获取到必要参数
			kw = dict(**request.match_info)
			 # 此时kw指向match_info属性，一个变量标识符的名字的dict列表。Request中获取的命名关键字参数必须要在这个dict当中
		else:
			if not self._has_var_kw_arg and self._named_kw_args:#有KEYWORD_ONLY参数没有VAR_KEYWORD
				copy = dict()
				for name in self._named_kw_args:
					if name in kw:
						copy[name] = kw[name]#找到request中参数与函数参数相同的，保存下来
				kw = copy
			for k,v in request.match_info.items():
				if k in kw:
						logging.warning('Duplicate arg name in named arg and kw args: %s' % k)  # 命名参数和关键字参数有名字重复
				kw[k] = v
		if self._has_request_arg:
			kw['request'] = request
		#检查函数是否有必要关键字参数，KW中如果没有返回错误信息
		if self._required_kw_args:
			for name in self._required_kw_args:
				if not name in kw:
					return web.HTTPBadRequest('Missing argument: %s' % name)
		logging.info('call with args: %s' % str(kw))
		try:
			r = yield from self._func(**kw)#给URL处理函数传入对应的参数，执行URL处理函数
			return r
		except APIError as e:
			return dict(error=e.error, data=e.data, message=e.message)
			
			
# 添加静态页面的路径
def add_static(app):
	path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
	app.router.add_static('/static/',path) 
	logging.info('add static %s => %s' % ('/static/', path))
	
#注册一个URL处理函数
def add_route(app,fn):
	method = getattr(fn,'__method__',None)
	path = getattr(fn,'__route__',None)
	if path is None or method is None:
		raise ValueError('@get or @post not defined in %s.' % str(fn))
	if not asyncio.iscoroutine(fn) and  not inspect.isgeneratorfunction(fn):
		fn = asyncio.coroutine(fn)#处理URL函数必须是协程
	logging.info('add route %s %s => %s (%s)' % (method, path, fn.__name__, ', '.join(inspect.signature(fn).parameters.keys())))
	app.router.add_route(method, path, RequestHandler(app, fn))

#把整个包内的处理URL函数批量注册
def add_routes(app,module_name):
	n = module_name.rfind('.')#rfind() 返回字符串最后一次出现的位置，如果没有匹配项则返回-1。没有'.',则传入的是module名，因为文件都有后缀名
	logging.info('n = %s',n)
	if n == (-1):
		mod = __import__(module_name,globals(),locals())
		logging.info('globals = %s', globals()['__name__'])
	else:
		mod = __import__(module_name[:n],globals(),locals())
	
	for attr in dir(mod):
		if attr.startswith('_'):#我们定义的方法一定不以下划线开头
			continue
		fn = getattr(mod,attr)#获取包内的方法或者属性
		if callable(fn):#能调用的是方法
			method = getattr(fn,'__method__',None)
			path = getattr(fn,'__route__',None)
			if method and path:#有method和path的是我们定义的URL处理方法
				add_route(app,fn)
