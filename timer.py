from friend_import import *

if TYPE_CHECKING:
    from friend import MyBot

class Timer:
    __emoji = "\U0001F504"

    def __init__(self,
                 bot: 'MyBot',
                 ch: discord.TextChannel,
                 name: str,
                 seconds: Union[float, d],
                 async_callback=None,
                 args=None):
        self.bot = bot
        self.bot.timers[name] = self
        self.channel: discord.TextChannel = ch
        self.name: str = name
        self.seconds: float = seconds
        self.start_time: datetime.datetime = datetime.datetime.utcnow()
        self.loop = self.bot.loop
        self.message: Optional[discord.Message] = None
        self.done = False
        self.callback = async_callback
        self.args = args
        if self.args is None:
            self.args = tuple()

        self.task: asyncio.Task = self.loop.create_task(self.run())
        self.sub_task: Optional[asyncio.Task] = None

    def __str__(self):
        return f"Timer({self.name})"

    async def run(self):
        try:
            print(f"[{get_nowtime_str()}] {self}: Timer start.")
            self.message = await self.channel.send(embed=discord.Embed(
                title="Timer start!",
                description=f"Timer Name : `{self.name}`\n"
                            f"Time Limit : {self.seconds}",
                color=discord.Colour.dark_orange()
            ))
            await self.message.add_reaction(self.__emoji)
            self.sub_task = self.loop.create_task(self.sub_run())
            if self.seconds < 10:
                await asyncio.sleep(self.seconds)
            else:
                await asyncio.sleep(self.seconds - 10)
                await asyncio.gather(
                    asyncio.sleep(10),
                    self.channel.send(f"**:bangbang: | Timer `{self.name}` has 10 seconds remaining!**")
                )
            await self.timeover()
        except asyncio.CancelledError:
            return
        except GeneratorExit:
            return
        except BaseException as ex_:
            print("[@] Timer.run:")
            print(get_traceback_str(ex_))
            raise ex_

    def __check(self, react, usr):
        return react.message == self.message and str(react.emoji) == self.__emoji and not usr.bot

    async def sub_run(self):
        try:
            while True:
                done, pending = await asyncio.wait(
                    [
                        self.bot.wait_for('reaction_add', check=self.__check),
                        self.bot.wait_for('reaction_remove', check=self.__check)
                    ], return_when=asyncio.FIRST_COMPLETED
                )
                for pt in pending:
                    pt.cancel()
                react, user = await done.pop()
                await self.edit()
        except asyncio.CancelledError:
            return
        except BaseException as ex_:
            print("[@] Timer.sub_run:")
            print(get_traceback_str(ex_))
            raise ex_

    async def edit(self):
        if self.done:
            return
        await self.message.edit(embed=discord.Embed(
                title="TIMER RUNNING...",
                description=f"Timer Name : `{self.name}`\n"
                            f"Time Limit : {self.seconds}\n"
                            f"Time Left : {self.left_sec()}",
                color=discord.Colour.dark_orange()
            ))

    async def timeover(self):
        if self.done: return
        self.done = True
        print(f"[{get_nowtime_str()}] {self}: Timer end. (time over)")
        self.sub_task.cancel()
        await self.message.edit(embed=discord.Embed(
            title="TIME OVER!",
            description=f"Timer Name : `{self.name}`\n"
                        f"Time Limit : {self.seconds}",
            color=discord.Colour.dark_grey()
        ))
        await self.call_back(False)

    async def cancel(self, run_call_back=True):
        if self.done: return
        self.done = True
        print(f"[{get_nowtime_str()}] {self}: Timer end. (cancelled)")
        self.task.cancel()
        self.sub_task.cancel()
        await self.message.edit(embed=discord.Embed(
            title="TIMER STOPPED!",
            description=f"Timer Name : `{self.name}`\n"
                        f"Time Limit : {self.seconds}\n"
                        f"Time Left : {self.left_sec()}",
            color=discord.Colour.dark_red()
        ))
        if run_call_back:
            await self.call_back(True)

    async def call_back(self, cancelled):
        print(f"[{get_nowtime_str()}] {self}: Running call_back.")
        del self.bot.timers[self.name]
        if self.callback is None:
            return
        await self.callback(cancelled, *self.args)

    def left_sec(self) -> float:
        return round(self.seconds - ((datetime.datetime.utcnow() - self.start_time).total_seconds()), 6)

