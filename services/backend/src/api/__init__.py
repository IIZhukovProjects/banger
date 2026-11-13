from .game.handler import Game
from .game.images.handler import GameImages
from .images.handler import Images
from .metadata.handler import Metadata
from .rooms.handler import Rooms
from .rooms.players.handler import RoomsPlayers


def delegates():
    return [Game(), GameImages(), Images(), Metadata(), Rooms(), RoomsPlayers()]
