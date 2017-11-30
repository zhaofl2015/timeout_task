# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import sys
import os
from logging.handlers import RotatingFileHandler

__author__ = 'zhaofl2015'

import json
import urllib2
import redis
import time
from config import ZyConfig
import logging


"""
    超时通知器

    !!! IMPORTANT
    以LIb方式注册回调的函数，建议使用返回True或者False，或者0值或者非零值的方式。当回调不成功的时候，将保存注册的键，下一个周期再次调用。
    用于当前超时已到，但是并不满足指定条件。
    若不返回值，则默认执行成功，删除指定的键。

    1.注册命名空间键值，并指定owner，以及对应工程中的回调的module，class，func。如果是Standalone的函数，不需要指定class_name.最后指定回调方式。
       如：lib，采用同工程中执行lib的方式。url（待开发）

       sample：
        TimeoutNotifier.register_timeout_notifier('correction', 'fanglei.zhao', {
            'module_name': 'models.voice_tag_models',
            'class_name': 'BatchTag',
            'func_name': 'clear_assignments',
        }, 'lib')

    2.设定之前指定命名空间，要超时的键，及超时的时长，（秒）
       sample:
        TimeoutNotifier.set_timeout('correction', 'Q_2333333', 1)

    3.使用linux的crontab或者起一个standalone的server，定时的执行该任务
        TimeoutNotifier.call_back_crontab()

    TODO：
        a.url方式的回调（支持验证模式的回调)
        b.单独起一个server的实例

"""

logger = logging.getLogger('timeout')

if sys.platform != 'linux2':
    log_dir = ZyConfig.root_path + ur'\logs'
else:
    log_dir = ZyConfig.log_dir

if os.path.isdir(log_dir) is False:
    os.makedirs(log_dir)

abs_filename = os.path.join(log_dir, 'timeout.log')

handler = RotatingFileHandler(abs_filename, maxBytes=10 * 1024 * 1024, backupCount=5)
handler.setFormatter(logging.Formatter(fmt='%(levelname)s %(asctime)s %(filename)s %(funcName)s %(message)s'))
logger.addHandler(handler)
# streaming_handler = logging.StreamHandler()
# logger.addHandler(streaming_handler)

logger.setLevel(logging.DEBUG)


class TimeoutNotifier(object):
    """
    超时通知器
    """
    _redis = redis.Redis(
        host=ZyConfig.cache['CACHE_REDIS_HOST'],
        port=ZyConfig.cache['CACHE_REDIS_PORT'],
        db=2,
        socket_connect_timeout=3,
        socket_timeout=3
    )
    all_key = '_all_key_names'
    interval = 0.001

    @classmethod
    def set_all_key(cls, all_key):
        cls.all_key = all_key

    @classmethod
    def set_interval(cls, interval):
        cls.interval = interval

    @classmethod
    def __lock(cls, key_name):
        if cls._redis.hincrby(key_name, 'busy', 1) == 1:
            return True
        else:
            return False

    @classmethod
    def __unlock(cls, key_name):
        cls._redis.hset(key_name, 'busy', 0)

    @classmethod
    def register_timeout_notifier(cls, key_name, owner, url_or_libinfo, call_type='lib'):
        key_owner = cls._redis.hget(key_name, 'owner')
        if not key_owner or key_owner == owner:
            cls._redis.hset(key_name, 'owner', owner)
            cls._redis.hset(key_name, 'busy', 0)
            cls._redis.hset(key_name, 'call_type', call_type)
            if call_type == 'url':
                cls._redis.hset(key_name, 'url', url_or_libinfo)
            elif call_type == 'lib':
                cls._redis.hset(key_name, 'lib', json.dumps(url_or_libinfo))
            cls._redis.sadd(cls.all_key, key_name)
            return True, ''
        else:
            logger.warning('%s is attempted by %s' % (key_name, owner))
            return False, 'name: %s is already taken by %s' % (key_name, key_owner)

    @classmethod
    def set_timeout(cls, key_name, item, timeout):
        """
        :param key_name:
        :param item:
        :param timeout:  以秒为单位
        :return:
        """
        # todo 此处持续等待？
        if cls._redis.hget(key_name, 'owner') is None:
            return False
        while True:
            if cls.__lock(key_name):
                cls._redis.zadd("%s_zset" % key_name, item, int(time.time()) + timeout)
                cls.__unlock(key_name)
                logger.debug('set key success %s' % item)
                break
            else:
                time.sleep(cls.interval)
        return True

    @classmethod
    def call_back_crontab(cls, **kwargs):
        """
        默认并建议每分钟执行一次，使用linux的crontab.
        更细粒度，需要起server
        :param call_back_type:
        :param kwargs:
        :return:
        """
        # todo 添加登录认证等信息。如果访问的接口需要认证，添加认证需要的url，postdata。否则直接访问接口
        # todo 如果有太多的超时，则下次执行跳过
        for key_name in cls._redis.smembers(cls.all_key):
            for item in cls._redis.zrangebyscore('%s_zset' % key_name, 0, int(time.time())):
                value = cls._redis.hgetall(key_name)
                call_back_type = value['call_type']

                # if call_back_type == 'url':
                #     try:
                #         url = cls._redis.hget(key_name, 'url')
                #         if url is None:
                #             continue
                #         ret = urllib2.urlopen('http://' + url + item, timeout=10).read()
                #     except:
                #         # 此处多次失败，可报警
                #         continue
                #
                #     data = json.loads(ret)
                #     if data.get('success', False) is True:
                #         while True:
                #             if cls.__lock(key_name):
                #                 cls._redis.zrem('%s_zset' % key_name, item)
                #                 # print 'zrem %s' % item
                #                 cls.__unlock(key_name)
                #                 break
                #             else:
                #                 time.sleep(cls.interval)
                #     else:
                #         continue
                if call_back_type == 'lib':
                    try:
                        lib_data = json.loads(value['lib'])
                        module_name = lib_data.get('module_name')
                        class_name = lib_data.get('class_name')
                        func_name = lib_data.get('func_name')
                        __import__(module_name)
                        mod = sys.modules[module_name]
                        if class_name:
                            if callable(getattr(mod.__dict__[class_name], func_name)):

                                ret = getattr(mod.__dict__[class_name], func_name)(item)
                            else:
                                ret = False
                                logger.info('class method %s is not callable, module %s, class %s'
                                            % (func_name, module_name, class_name))
                        else:
                            if callable(mod.__dict__[func_name]):
                                ret = mod.__dict__[func_name](item)
                            else:
                                ret = False
                                logger.info('standalone function %s not callable, module %s'
                                            % (func_name, module_name))
                        if ret or ret is None:
                            logger.info('run success %s with args %s' % (func_name, item))
                            while True:
                                if cls.__lock(key_name):
                                    cls._redis.zrem('%s_zset' % key_name, item)
                                    cls.__unlock(key_name)
                                    break
                                else:
                                    time.sleep(cls.interval)
                    except ImportError, e:
                        logger.error('try to import not exists module, error info: %s' % e)
                        continue
                    except KeyError, e:
                        logger.error('no key found, error info: %s' % e)
                        continue
                    except Exception, e:
                        logger.error('error info: %s' % e)
                        continue


if __name__ == '__main__':
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    # TimeoutNotifier.register_timeout_notifier('correction', 'fanglei.zhao', {
    #     'module_name': 'models.voice_tag_models',
    #     # 'class_name': 'BatchTag',
    #     'func_name': 'clear_assignments',
    # }, 'lib')
    # TimeoutNotifier.set_timeout('correction', 'Q_2333333', 1)
    # TimeoutNotifier.call_back_crontab()
    def funca():
        logger.info('hahaha')
    funca()
    pass
