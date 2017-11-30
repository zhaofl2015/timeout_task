
超时通知器

    !!! IMPORTANT
    
    以LIB方式注册回调的函数，建议使用返回True或者False，或者0值或者非零值的方式。当回调不成功的时候，将保存注册的键，下一个周期再次调用。
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
