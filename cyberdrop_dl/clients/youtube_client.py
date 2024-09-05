from cyberdrop_dl.clients.download_client import DownloadClient    from cyberdrop_dl.managers.client_manager import ClientManager
    from cyberdrop_dl.managers.manager import Manager

class YoutubeClient(DownloadClient):
    def __init__(self, manager: Manager, client_manager: ClientManager):
        super().__init__(manager, client_manager)
      
