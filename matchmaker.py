from friend_import import *
from match import MatchScrim

if TYPE_CHECKING:
    from friend import MyBot


class WaitingPlayer:
    def __init__(self, bot: 'MyBot', discord_member: discord.Member):
        self.bot = bot
        self.loop = bot.loop
        self.player = discord_member
        self.player_rating = 0
        self.target_rating_low = 0
        self.target_rating_high = 0
        self.dr = 200
        self.task = self.loop.create_task(self.expanding())

    def __repr__(self):
        return self.player.name

    async def expanding(self):
        puuid = self.bot.uuid.get(self.player.id)
        if puuid is None:
            self.player_rating = (await self.bot.get_user_info(self.player.id))['elo']
        else:
            self.player_rating = (await self.bot.get_user_info(puuid))['elo']
        self.target_rating_low = self.player_rating
        self.target_rating_high = self.player_rating
        try:
            while True:
                await asyncio.sleep(1)
                dr = self.dr / (self.bot.matchmaker.count + 9)
                self.target_rating_low -= self.dr
                self.target_rating_high += self.dr
        except asyncio.CancelledError:
            raise
        except BaseException as ex_:
            print(get_traceback_str(ex_))
            raise ex_


class MatchMaker:
    def __init__(self, bot: 'MyBot'):
        self.bot = bot
        self.loop = bot.loop
        self.pool: deque[WaitingPlayer] = deque()
        self.players_in_pool: set[int] = set()
        self.task = self.loop.create_task(self.check_match())
        self.querys = deque()

    def add_player(self, player: discord.Member):
        self.querys.append((1, player))

    def remove_player(self, player: discord.Member):
        self.querys.append((2, player))
    
    @property
    def count(self):
        return len(self.players_in_pool)

    async def check_match(self):
        try:
            while True:
                i = 0
                while i < len(self.pool):
                    p = self.pool.popleft()
                    opponents = set(filter(lambda o: p.target_rating_low <= o.player_rating <= p.target_rating_high,
                                           self.pool))
                    if len(opponents) > 0:
                        opponent = min(opponents, key=lambda o: abs(o.player_rating - p.player_rating))
                        self.pool.remove(opponent)
                        self.bot.matches[p.player] = self.bot.matches[opponent.player] = m = \
                            MatchScrim(self.bot, p.player, opponent.player)
                        await m.do_match_start()
                        self.players_in_pool.remove(p.player.id)
                        self.players_in_pool.remove(opponent.player.id)
                        p.task.cancel()
                        opponent.task.cancel()
                        print(f"[{get_nowtime_str()}] MatchMaker: Match found!\n"
                              f"PLAYER   : {p.player.name}\n"
                              f"OPPONENT : {opponent.player.name}")
                    else:
                        self.pool.append(p)
                        i += 1
                while len(self.querys) > 0:
                    method, player = self.querys.popleft()
                    if method == 1:
                        if player.id not in self.players_in_pool:
                            self.pool.append(WaitingPlayer(self.bot, player))
                            self.players_in_pool.add(player.id)
                            print(f"[{get_nowtime_str()}] MatchMaker: {player.name} queued.")
                        else:
                            print(f"[{get_nowtime_str()}] MatchMaker: {player.name} already queued.")
                    else:
                        if len(self.pool) == 0:
                            continue
                        elif self.pool[-1].player.id == player.id:
                            p = self.pool.pop()
                            p.task.cancel()
                            self.players_in_pool.remove(p.player.id)
                            print(f"[{get_nowtime_str()}] MatchMaker: {player.name} unqueued.")
                        else:
                            for i in range(len(self.pool) - 1):
                                p = self.pool.popleft()
                                if p.player.id == player.id:
                                    p.task.cancel()
                                    self.pool.remove(p)
                                    self.players_in_pool.remove(p.player.id)
                                    print(f"[{get_nowtime_str()}] MatchMaker: {player.name} unqueued.")
                    print(f"[{get_nowtime_str()}] MatchMaker: Now LEN of variables:\n"
                          f"players_in_pool : {len(self.players_in_pool)}\n"
                          f"pool            : {len(self.pool)}")
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            raise

    def close(self):
        self.task.cancel()
        for p in self.pool:
            p.task.cancel()

