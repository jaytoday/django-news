import os

def locking(func):
    """
    Locking to prevent dogpiling
    """
    def perform_locking(*args, **kwargs):
        lock_dir = os.path.join(os.path.dirname(__file__), '.lockdir')
        if not os.path.exists(lock_dir):
            try:
                os.mkdir(lock_dir)
                return func(*args, **kwargs)
            finally:
                os.rmdir(lock_dir)
        else:
            pass
    
    return perform_locking
