import config_default

#重写属性设置，获取方法
#支持通过属性名访问键值对的值，属性名将被当做键名

class Dict(dict):
	def __init__(self,names=(),values=(),**kw):
		super(Dict,self).__init__(**kw)
		for k,v in zip(names,values):
			self[k]=v
	def __getattr__(self, item):
		try:
			return self[item]
		except KeyError:
			raise AttributeError(r"'Dict' object has no attribute '%s'" % item)

	def __setattr__(self, key, value):
		self[key] = value

def merge(default, override):
	r = {}
	for k, v in default.items():
		if k in override:
			if isinstance(v, dict):
				r[k] = merge(v, override[k])#递归调用
			else:
				r[k] = override[k]
		else:
			r[k] = v
	return r

#把merge后的结果编程Dict类的一个实例
def toDict(d):
	D = Dict()
	for k, v in d.items():
		D[k] = toDict(v) if isinstance(v, dict) else v
	return D

configs = config_default.configs

try:
	import config_override
	configs = merge(configs, config_override.configs)
except ImportError:
	pass
	
configs = toDict(configs)