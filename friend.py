from friend_import import *
from timer import Timer
from scrim import Scrim
from match import Match_Scrim
from matchmaker import MatchMaker

class MyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"[{time.strftime('%Y-%m-%d %a %X', time.localtime(time.time()))}]")
        print("BOT NAME :", self.bot.user.name)
        print("BOT ID   :", self.bot.user.id)
        game = discord.Game("m;help")
        await self.bot.change_presence(status=discord.Status.online, activity=game)
        print("==========BOT START==========")
        self.bot.match_category_channel = await self.bot.fetch_channel(824985957165957151)

    @commands.Cog.listener()
    async def on_message(self, message):
        ch = message.channel
        p = message.author
        if p == self.bot.user:
            return
        if isinstance(message.channel, discord.channel.DMChannel):
            print(
                f"[{time.strftime('%Y-%m-%d %a %X', time.localtime(time.time()))}] "
                f"[DM] <{p.name};{p.id}> {message.content}"
            )
        else:
            print(
                f"[{time.strftime('%Y-%m-%d %a %X', time.localtime(time.time()))}] "
                f"[{message.guild.name};{ch.name}] <{p.name};{p.id}> {message.content}"
            )
        if credentials.expired:
            gs.login()
        pm = self.bot.matches.get(p)
        if message.content == 'rdy' and pm is not None and ch == pm.channel:
            await pm.switch_ready(p)

    @commands.Cog.listener()
    async def on_command_exception(self, ctx, exception):
        exceptiontxt = get_traceback_str(exception)
        print('================ ERROR ================')
        print(exceptiontxt)
        print('=======================================')
        await ctx.send(f'Error Occurred :\n```{exceptiontxt}```')

    @commands.command(name="help")
    async def _help(self, ctx):
        await ctx.send(embed=helptxt)

    @commands.command()
    async def ping(self, ctx):
        msgtime = ctx.message.created_at
        nowtime = datetime.datetime.utcnow()
        print(msgtime)
        print(nowtime)
        await ctx.send(f"Pong! `{(nowtime - msgtime).total_seconds() * 1000 :.4f}ms`")

    @commands.command()
    async def roll(self, ctx, *dices: str):
        sendtxt = []
        for _d in dices:
            x = dice(_d)
            if not x:
                continue
            sendtxt.append(f"{_d}: **{' / '.join(x)}**")
        await ctx.send(embed=discord.Embed(title="Dice result", description='\n'.join(sendtxt)))

    @commands.command()
    async def sheetslink(self, ctx):
        await ctx.send("https://docs.google.com/spreadsheets/d/1SA2u-KgTsHcXcsGEbrcfqWugY7sgHIYJpPa5fxNEJYc/edit#gid=0")

    @commands.command()
    @is_owner()
    async def say(self, ctx, *, txt: str):
        if txt:
            await ctx.send(txt)

    @commands.command()
    @is_owner()
    async def sayresult(self, ctx, *, com: str):
        res = eval(com)
        await ctx.send('Result : `' + str(res) + '`')

    @commands.command()
    @is_owner()
    async def run(self, ctx, *, com: str):
        exec(com)
        await ctx.send('Done')

    @commands.command()
    @is_owner()
    async def asyncrun(self, ctx, *, com: str):
        exec(
            f'async def __ex(): ' +
            ''.join(f'\n    {_l}' for _l in com.split('\n')),
            {**globals(), **locals()}, locals()
        )
        await locals()['__ex']()
        await ctx.send('Done')

    @commands.command()
    async def make(self, ctx):
        s = self.bot.datas[ctx.guild.id][ctx.channel.id]
        if s['valid']:
            await ctx.send(embed=discord.Embed(
                title="There's already scrim running.",
                description=f"You can make scrim only one per channel.",
                color=discord.Colour.dark_red()
            ))
            return
        s['valid'] = 1
        s['scrim'] = Scrim(self.bot, ctx.channel)
        await ctx.send(embed=discord.Embed(
            title="A SCRIM IS MADE.",
            description=f"Guild : {ctx.guild}\nChannel : {ctx.channel}",
            color=discord.Colour.green()
        ))
        if self.bot.shutdown_datetime - datetime.datetime.now(tz=KST) <= datetime.timedelta(hours=1):
            await ctx.send(embed=discord.Embed(
                title=f"The bot is supposed to shutdown at {self.bot.shutdown_datetime.strftime('%H:%M')} KST.",
                description="If the bot shutdowns during the match, "
                            "all datas of the match will be disappeared.",
                color=discord.Colour.dark_red()
            ))

    @commands.command(aliases=['t'])
    async def teamadd(self, ctx, *, name):
        s = self.bot.datas[ctx.guild.id][ctx.channel.id]
        if s['valid']:
            await s['scrim'].maketeam(name)

    @commands.command(aliases=['tr'])
    async def teamremove(self, ctx, *, name):
        s = self.bot.datas[ctx.guild.id][ctx.channel.id]
        if s['valid']:
            await s['scrim'].removeteam(name)

    @commands.command(name="in")
    async def _in(self, ctx, *, name):
        s = self.bot.datas[ctx.guild.id][ctx.channel.id]
        if s['valid']:
            await s['scrim'].addplayer(name, ctx.author)

    @commands.command()
    async def out(self, ctx):
        s = self.bot.datas[ctx.guild.id][ctx.channel.id]
        if s['valid']:
            await s['scrim'].removeplayer(ctx.author)

    @commands.command(aliases=['score', 'sc'])
    async def _score(self, ctx, sc: int, a: float = 0.0, m: int = 0):
        s = self.bot.datas[ctx.guild.id][ctx.channel.id]
        if s['valid']:
            await s['scrim'].addscore(ctx.author, sc, a, m)

    @commands.command(aliases=['scr'])
    async def scoreremove(self, ctx):
        s = self.bot.datas[ctx.guild.id][ctx.channel.id]
        if s['valid']:
            await s['scrim'].removescore(ctx.author)

    @commands.command()
    async def submit(self, ctx, calcmode: Optional[str] = None):
        s = self.bot.datas[ctx.guild.id][ctx.channel.id]
        if s['valid']:
            await s['scrim'].submit(calcmode)

    @commands.command()
    async def start(self, ctx):
        s = self.bot.datas[ctx.guild.id][ctx.channel.id]
        if s['valid']:
            await s['scrim'].do_match_start()

    @commands.command()
    async def abort(self, ctx):
        s = self.bot.datas[ctx.guild.id][ctx.channel.id]
        if s['valid']:
            if not s['scrim'].match_task.done():
                s['scrim'].match_task.cancel()

    @commands.command()
    async def end(self, ctx):
        s = self.bot.datas[ctx.guild.id][ctx.channel.id]
        if s['valid']:
            await s['scrim'].end()
            del self.bot.datas[ctx.guild.id][ctx.channel.id]

    @commands.command()
    async def bind(self, ctx, number: int):
        mid = ctx.author.id
        self.bot.uids[mid] = number
        if self.bot.ratings[number] == d():
            self.bot.ratings[number] = elo_rating.ELO_MID_RATING - (await get_rank(number)) / d('100')
        await ctx.send(embed=discord.Embed(
            title=f'Player {ctx.author.name} binded to UID {number}.',
            color=discord.Colour(0xfefefe)
        ))

    @commands.command(name="map")
    async def _map(self, ctx, *, name: str):
        s = self.bot.datas[ctx.guild.id][ctx.channel.id]
        if s['valid']:
            resultmessage = await ctx.send(embed=discord.Embed(
                title="Calculating...",
                color=discord.Colour.orange()
            ))
            scrim = s['scrim']
            t = scrim.setmapinfo(name)
            if t:
                try:
                    target = worksheet.find(name)
                except gspread.exceptions.CellNotFound:
                    await resultmessage.edit(embed=discord.Embed(
                        title=f"{name} not found!",
                        description="Check typo(s), and if that name is on bot sheet.",
                        color=discord.Colour.dark_red()
                    ))
                    return
                except Exception as e:
                    await resultmessage.eddit(embed=discord.Embed(
                        title="Error occurred!",
                        description=f"Error : `[{type(e)}] {e}`",
                        color=discord.Colour.dark_red()
                    ))
                    return
                values = worksheet.row_values(target.row)
                scrim.setfuncs['author'](values[0])
                scrim.setfuncs['artist'](values[1])
                scrim.setfuncs['title'](values[2])
                scrim.setfuncs['diff'](values[3])
                mapautosc = values[4]
                maptime_ = values[8]
                if mapautosc:
                    scrim.setautoscore(int(mapautosc))
                if maptime_:
                    scrim.setmaptime(int(maptime_))
                scrim.setnumber(name)
                scrim.setmode(re.findall('|'.join(modes), name.split(';')[-1])[0])
            await resultmessage.edit(embed=discord.Embed(
                title=f"Map infos Modified!",
                description=f"Map Info : `{scrim.getmapfull()}`\n"
                            f"Map Number : {scrim.getnumber()} / Map Mode : {scrim.getmode()}\n"
                            f"Map SS Score : {scrim.getautoscore()} / Map Length : {scrim.getmaptime()} sec.",
                color=discord.Colour.blue()
            ))

    @commands.command(aliases=['mm'])
    async def mapmode(self, ctx, mode: str):
        s = self.bot.datas[ctx.guild.id][ctx.channel.id]
        if s['valid']:
            resultmessage = await ctx.send(embed=discord.Embed(
                title="계산 중...",
                color=discord.Colour.orange()
            ))
            scrim = s['scrim']
            scrim.setmode(mode)
            await resultmessage.edit(embed=discord.Embed(
                title=f"Map infos Modified!",
                description=f"Map Info : `{scrim.getmapfull()}`\n"
                            f"Map Number : {scrim.getnumber()} / Map Mode : {scrim.getmode()}\n"
                            f"Map SS Score : {scrim.getautoscore()} / Map Length : {scrim.getmaptime()} sec.",
                color=discord.Colour.blue()
            ))

    @commands.command(aliases=['mt'])
    async def maptime(self, ctx, _time: int):
        s = self.bot.datas[ctx.guild.id][ctx.channel.id]
        if s['valid']:
            resultmessage = await ctx.send(embed=discord.Embed(
                title="계산 중...",
                color=discord.Colour.orange()
            ))
            scrim = s['scrim']
            scrim.setmaptime(_time)
            await resultmessage.edit(embed=discord.Embed(
                title=f"Map infos Modified!",
                description=f"Map Info : `{scrim.getmapfull()}`\n"
                            f"Map Number : {scrim.getnumber()} / Map Mode : {scrim.getmode()}\n"
                            f"Map SS Score : {scrim.getautoscore()} / Map Length : {scrim.getmaptime()} sec.",
                color=discord.Colour.blue()
            ))

    @commands.command(aliases=['ms'])
    async def mapscore(self, ctx, sc_or_auto: Union[int, str], *, path: Optional[str] = None):
        s = self.bot.datas[ctx.guild.id][ctx.channel.id]
        if s['valid']:
            resultmessage = await ctx.send(embed=discord.Embed(
                title="Processing...",
                color=discord.Colour.orange()
            ))
            scrim = s['scrim']
            if sc_or_auto == 'auto':
                s = scoreCalc.scoreCalc(path)
                scrim.setautoscore(s.getAutoScore()[1])
                s.close()
            else:
                scrim.setautoscore(sc_or_auto)
            await resultmessage.edit(embed=discord.Embed(
                title=f"Map infos Modified!",
                description=f"Map Info : `{scrim.getmapfull()}`\n"
                            f"Map Number : {scrim.getnumber()} / Map Mode : {scrim.getmode()}\n"
                            f"Map SS Score : {scrim.getautoscore()} / Map Length : {scrim.getmaptime()} sec.",
                color=discord.Colour.blue()
            ))

    @commands.command(aliases=['l'])
    async def onlineload(self, ctx, checkbit: Optional[int] = None):
        s = self.bot.datas[ctx.guild.id][ctx.channel.id]
        if s['valid']:
            await s['scrim'].onlineload(checkbit)

    @commands.command()
    async def form(self, ctx, *, f_: str):
        s = self.bot.datas[ctx.guild.id][ctx.channel.id]
        if s['valid']:
            await s['scrim'].setform(f_)

    @commands.command(aliases=['mr'])
    async def mapmoderule(
            self,
            ctx,
            nm: Optional[str],
            hd: Optional[str],
            hr: Optional[str],
            dt: Optional[str],
            fm: Optional[str],
            tb: Optional[str]
    ):
        s = self.bot.datas[ctx.guild.id][ctx.channel.id]
        if s['valid']:
            def temp(x: Optional[str]):
                return set(map(int, x.split(',')))

            s['scrim'].setmoderule(temp(nm), temp(hd), temp(hr), temp(dt), temp(fm), temp(tb))

    @commands.command()
    async def timer(self, ctx, action: Union[float, str], name: Optional[str] = None):
        if action == 'now':
            if self.bot.timers.get(name) is None:
                await ctx.send(embed=discord.Embed(
                    title=f"No timer named `{name}`!",
                    color=discord.Colour.dark_red()
                ))
            else:
                await self.bot.timers[name].edit()
        elif action == 'cancel':
            if self.bot.timers.get(name) is None:
                await ctx.send(embed=discord.Embed(
                    title=f"No timer named `{name}`!",
                    color=discord.Colour.dark_red()
                ))
            else:
                await self.bot.timers[name].cancel()
        else:
            if name is None:
                name = str(self.bot.timer_count)
                self.bot.timer_count += 1
            if self.bot.timers.get(name) is not None and not self.bot.timers[name].done:
                await ctx.send(embed=discord.Embed(
                    title=f"There's already running timer named `{name}`!",
                    color=discord.Colour.dark_red()
                ))
                return
            try:
                Timer(self.bot, ctx.channel, name, float(action))
            except ValueError:
                await ctx.send(embed=discord.Embed(
                    title=f"You should enter number for time limit!",
                    color=discord.Colour.dark_red()
                ))


    @commands.command()
    async def calc(self, ctx, kind: str, maxscore: d, score: d, acc: d, miss: d):
        if kind == "nero2":
            result = neroscorev2(maxscore, score, acc, miss)
        elif kind == "jet2":
            result = jetonetv2(maxscore, score, acc, miss)
        elif kind == "osu2":
            result = osuv2(maxscore, score, acc, miss)
        else:
            await ctx.send(embed=discord.Embed(
                title="Unknown Calculate Mode!",
                description="It should be (Empty), `nero2`, `jet2`, or `osu2`",
                color=discord.Colour.dark_red()
            ))
            return
        await ctx.send(embed=discord.Embed(
            title=f"Calculation result : ({kind})",
            description=f"maxscore = {maxscore}\n"
                        f"score = {score}\n"
                        f"acc = {acc}\n"
                        f"miss = {miss}\n\n"
                        f"calculated = **{result}**",
            color=discord.Colour.dark_blue()
        ))

    @commands.command()
    async def now(self, ctx):
        s = self.bot.datas[ctx.guild.id][ctx.channel.id]
        if s['valid']:
            scrim = s['scrim']
            e = discord.Embed(title="Now scrim info", color=discord.Colour.orange())
            for t in scrim.team:
                e.add_field(
                    name="Team " + t,
                    value='\n'.join([(await self.bot.getusername(x)) for x in scrim.team[t]])
                )
            await ctx.send(embed=e)

    @commands.command(aliases=['pfme'])
    async def profileme(self, ctx):
        e = discord.Embed(
            title=f"{ctx.author.display_name}'s profile",
            color=discord.Colour(0xdb6ee1)
        )
        e.add_field(
            name="UID",
            value=str(self.bot.uids[ctx.author.id])
        )
        e.add_field(
            name="Elo",
            value=str(self.bot.ratings[self.bot.uids[ctx.author.id]])
        )
        await ctx.send(embed=e)

    @commands.command(aliases=['q'])
    async def queue(self, ctx):
        if self.bot.matches.get(ctx.author):
            await ctx.send(embed=discord.Embed(
                title=f"You can't queue while playing match.",
                color=discord.Colour.dark_red()
            ))
            return
        elif self.bot.uids[ctx.author.id] == 0:
            await ctx.send(embed=discord.Embed(
                title=f"You should bind your UID first. Use `m;bind`",
                color=discord.Colour.dark_red()
            ))
            return
        elif self.bot.shutdown_datetime - datetime.datetime.now(tz=KST) <= datetime.timedelta(minutes=30):
            await ctx.send(embed=discord.Embed(
                title=f"The bot is supposed to shutdown at {self.bot.shutdown_datetime.strftime('%H:%M')} KST.",
                description=f"You can join the queue until 30 minutes before shutdown "
                            f"({(self.bot.shutdown_datetime - datetime.timedelta(minutes=30)).strftime('%H:%M')} KST).",
                color=discord.Colour.dark_red()
            ))
            return
        self.bot.matchmaker.add_player(ctx.author)
        await ctx.send(embed=discord.Embed(
            title=f"{ctx.author.display_name} queued.",
            description=f"(If you already in queue, this will be ignored.)\n"
                        f"Now the number of players in queue : {len(self.bot.matchmaker.pool)}",
            color=discord.Colour(0x78f7fb)
        ))

    @commands.command(aliases=['uq'])
    async def unqueue(self, ctx):
        self.bot.matchmaker.remove_player(ctx.author)
        await ctx.send(embed=discord.Embed(
            title=f"{ctx.author.display_name} unqueued.",
            description=f"**This request could be ignored.**\n"
                        f"Now the number of players in queue : {len(self.bot.matchmaker.pool)}",
            color=discord.Colour(0x78f7fb)
        ))

class MyBot(commands.Bot):
    def __init__(self, ses, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.member_names: Dict[int, str] = dict()
        self.datas: dd[Dict[int, dd[Dict[int, Dict[str, Union[int, 'Scrim']]], Callable[[], Dict]]]] = \
            dd(lambda: dd(lambda: {'valid': False, 'scrim': None}))

        self.session: Optional[aiohttp.ClientSession] = ses
        self.osuapi: Optional[OsuApi] = osuapi.OsuApi(api_key, connector=AHConnector())

        self.uids: dd[int, int] = dd(int)
        self.ratings: dd[int, d] = dd(d)
        with open('uids.txt', 'r') as uidf:
            while data := uidf.readline():
                discordid, userid = data.split(' ')
                self.uids[int(discordid)] = int(userid)
        with open('ratings.txt', 'r') as ratf:
            while data := ratf.readline():
                userid, r = data.split(' ')
                self.ratings[int(userid)] = getd(r)

        self.timers: dd[str, Optional['Timer']] = dd(lambda: None)
        self.timer_count = 0

        self.matches: Dict[discord.Member, 'Match_Scrim'] = dict()
        self.match_category_channel: Optional[discord.CategoryChannel] = None
        self.matchmaker = MatchMaker(self)

        self.shutdown_datetime = get_shutdown_datetime()

    async def getusername(self, x: int) -> str:
        if self.member_names.get(x) is None:
            user = self.get_user(x)
            if user is None:
                user = await self.fetch_user(x)
            self.member_names[x] = user.name
        return self.member_names[x]


async def _main():
    app = MyBot(ses=aiohttp.ClientSession(), command_prefix='m;', help_command=None, intents=intents)
    app.add_cog(MyCog(app))
    got_login = await osu_login(app.session)
    if got_login:
        turnoff = False
        try:
            res = await app.osuapi.get_user("peppy")
            assert res[0].user_id == 2
        except HTTPError:
            print("Invalid osu!API key")
            turnoff = True
        except AssertionError:
            print("Something went wrong")
            turnoff = True

        assert turnoff is False
        bot_task = asyncio.create_task(app.start(token))
        try:
            await auto_off(app.shutdown_datetime)
        except asyncio.CancelledError:
            print('_main() : Cancelled')
        except Exception as _ex:
            raise
        finally:
            with open('uids.txt', 'w') as f__:
                for u in app.uids:
                    f__.write(f"{u} {app.uids[u]}\n")
            with open('ratings.txt', 'w') as f__:
                for u in app.ratings:
                    f__.write(f"{u} {app.ratings[u]}\n")
            app.osuapi.close()
            await app.change_presence(status=discord.Status.offline)
            await app.loop.shutdown_asyncgens()
            app.loop.close()
            await app.close()
            if not bot_task.done():
                bot_task.cancel()
            await app.session.close()
            app.matchmaker.close()
            print('_main() : finally done')

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    main_run = loop.create_task(_main())
    try:
        loop.run_until_complete(main_run)
    except KeyboardInterrupt:
        print('Ctrl+C')
    except BaseException as ex:
        print(get_traceback_str(ex))
    finally:
        main_run.cancel()
        loop.run_until_complete(asyncio.sleep(1))
        loop.run_until_complete(loop.shutdown_asyncgens())
        print('Shutdown asyncgens done / close after 1 sec.')
        loop.run_until_complete(asyncio.sleep(1))
        loop.close()
        print('loop closed')
