"""
بوت ديسكورد لإعطاء رولات ألوان (Auto Color Roles) - نسخة الرتب الجاهزة
=========================================================================
هذي النسخة تستخدم رتب موجودة فعلياً بالسيرفر (عبر Role ID) بدل ما تنشئ
رتب جديدة. تكتب أمر /setup_colors مرة وحدة بالروم، فينزل إيمبيد فيه
بانر + قائمة اختيار مباشرة تحتوي كل الألوان + خيار "إزالة اللون".

أي عضو يختار لون:
  - يشيل أي رول لون سابق عنده (من نفس المجموعة).
  - يعطيه الرول الجديد.
أو يختار "❌ إزالة اللون":
  - يشيل أي رول لون عنده بدون ما يعطيه شي.

القائمة ثابتة بالروم وتشتغل حتى بعد إعادة تشغيل البوت (Persistent View).

المتطلبات:
  pip install -U discord.py

طريقة التشغيل:
  1. حط التوكن في متغير البيئة DISCORD_TOKEN أو مباشرة بالكود.
  2. تأكد إن رتبة البوت أعلى من كل رتب الألوان بترتيب الرتب بالسيرفر
     (Server Settings > Roles) حتى يقدر يعطيها/يشيلها.
  3. البوت يحتاج صلاحية Manage Roles + applications.commands عند الدعوة.
  4. شغّل: python color_roles_bot.py
  5. بأي روم تبيه، اكتب: /setup_colors
"""

import asyncio
import json
import os
import discord
from discord import app_commands
from PIL import Image, ImageDraw, ImageOps
from io import BytesIO
from discord.ext import commands

# ------------------ الإعدادات ------------------

TOKEN = os.getenv("DISCORD_TOKEN", "ضع_التوكن_هنا")

def asset_path(filename: str) -> str:
    """يدعم تشغيل الملف منفرداً أو من داخل مجلد الحزمة."""
    project_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = (
        os.path.join(project_dir, "assets", filename),
        os.path.join(project_dir, filename),
        os.path.join(project_dir, "attached_assets", filename),
        os.path.join(project_dir, "..", "attached_assets", filename),
    )
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return candidates[0]


# صور الإيمبد المحلية. يتم رفعها كمرفقات مع الرسالة حتى تظهر داخل Discord.
BANNER_IMAGE_PATH = asset_path("Info_2_1786478064015.png")
THUMBNAIL_IMAGE_PATH = asset_path("IMG_7380_1786478064015.png")
BORDER_IMAGE_PATH = asset_path("Line_2_1786478472978.png")
WELCOME_IMAGE_PATH = asset_path("image_1786557973245.png")
BANNER_ATTACHMENT_NAME = "neon_roles_banner.png"
THUMBNAIL_ATTACHMENT_NAME = "neon_server_icon.png"
BORDER_ATTACHMENT_NAME = "neon_line.png"
WELCOME_ATTACHMENT_NAME = "neon_welcome.png"

# قائمة الألوان: (الاسم المعروض, Role ID)
COLOR_ROLES = [
    ("اسود", 1491140058886045807),
    ("احمر", 1491140086236971270),
    ("ازرق", 1491140062140829928),
    ("بنفسجي", 1491140064288182435),
    ("وردي", 1491140067173990420),
    ("سماوي", 1491140070143430747),
    ("ابيض", 1491140083271733351),
]

# قيمة خاصة لخيار إزالة اللون بالقائمة
REMOVE_VALUE = "__remove_color__"

# -------------------------------------------------

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

ALL_COLOR_ROLE_IDS = {role_id for _, role_id in COLOR_ROLES}
COLOR_CHOICES = [
    app_commands.Choice(name=name, value=str(role_id))
    for name, role_id in COLOR_ROLES
]
SOCIAL_LINKS = []
WELCOME_CHANNELS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "welcome_channels.json",
)


def load_welcome_channels() -> dict[str, int]:
    try:
        with open(WELCOME_CHANNELS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
        return {str(guild_id): int(channel_id) for guild_id, channel_id in data.items()}
    except (FileNotFoundError, json.JSONDecodeError, ValueError, TypeError):
        return {}


def save_welcome_channels() -> None:
    with open(WELCOME_CHANNELS_FILE, "w", encoding="utf-8") as file:
        json.dump(WELCOME_CHANNELS, file, ensure_ascii=False, indent=2)


WELCOME_CHANNELS = load_welcome_channels()


def get_welcome_channel(guild: discord.Guild) -> discord.TextChannel | None:
    configured_channel_id = WELCOME_CHANNELS.get(str(guild.id))
    if configured_channel_id:
        configured_channel = guild.get_channel(configured_channel_id)
        if isinstance(configured_channel, discord.TextChannel):
            return configured_channel

    if isinstance(guild.system_channel, discord.TextChannel):
        return guild.system_channel

    if guild.me:
        for channel in guild.text_channels:
            permissions = channel.permissions_for(guild.me)
            if permissions.send_messages and permissions.attach_files:
                return channel
    return None


def get_color_role(guild: discord.Guild, role_id: str) -> discord.Role | None:
    return guild.get_role(int(role_id))


async def send_command_error(
    interaction: discord.Interaction,
    message: str,
) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


class ColorSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=name, value=str(role_id))
            for name, role_id in COLOR_ROLES
        ]
        # إضافة خيار إزالة اللون بآخر القائمة
        options.append(
            discord.SelectOption(
                label="إزالة اللون",
                value=REMOVE_VALUE,
                description="يشيل أي رول لون عندك",
            )
        )
        super().__init__(
            placeholder="اختر لون الرول...",
            min_values=1,
            max_values=1,
            options=options,
            # custom_id ثابت ضروري حتى تشتغل القائمة كـ Persistent View
            custom_id="color_role_select",
        )

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        member = interaction.user
        choice = self.values[0]

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            # إزالة أي رول لون سابق عند العضو
            roles_to_remove = [
                r for r in member.roles if r.id in ALL_COLOR_ROLE_IDS
            ]
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason="تبديل/إزالة رول اللون")

            if choice == REMOVE_VALUE:
                await interaction.followup.send(
                    "✅ تم إزالة رول اللون عنك.", ephemeral=True
                )
                return

            role_id = int(choice)
            role = guild.get_role(role_id)
            if role is None:
                await interaction.followup.send(
                    "❌ الرتبة مو موجودة بالسيرفر (تأكد من الـ Role ID).",
                    ephemeral=True,
                )
                return

            await member.add_roles(role, reason="اختيار رول لون")
            await interaction.followup.send(
                f"✅ تم إعطاؤك رول اللون: **{role.name}**", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ ما عندي صلاحية كافية. تأكد إن رتبة البوت أعلى من رولات الألوان "
                "وإن عنده صلاحية Manage Roles.",
                ephemeral=True,
            )


class ColorView(discord.ui.View):
    def __init__(self):
        # timeout=None ضروري حتى تبقى القائمة شغالة للأبد
        super().__init__(timeout=None)
        self.add_item(ColorSelect())


@bot.event
async def create_welcome_image(member: discord.Member) -> BytesIO | None:
    """يضع صورة العضو داخل الدائرة الموجودة في قالب الترحيب."""
    if not os.path.exists(WELCOME_IMAGE_PATH):
        return None

    try:
        # صورة القالب الأساسية
        base = Image.open(WELCOME_IMAGE_PATH).convert("RGBA")

        # جلب صورة العضو من ديسكورد بجودة عالية
        avatar_bytes = await member.display_avatar.read()
        avatar = Image.open(BytesIO(avatar_bytes)).convert("RGBA")

        # أبعاد وموقع الدائرة في قالب neon_welcome.png
        center_x, center_y = 336, 229
        radius = 121
        diameter = radius * 2

        # قص صورة العضو لتصبح مربعة ثم نلائمها داخل الدائرة
        avatar = ImageOps.fit(avatar, (diameter, diameter), method=Image.Resampling.LANCZOS)

        # قناع دائري حتى لا تخرج صورة العضو عن الدائرة
        mask = Image.new("L", (diameter, diameter), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, diameter - 1, diameter - 1), fill=255)

        # وضع صورة العضو مكان الصورة القديمة
        base.paste(avatar, (center_x - radius, center_y - radius), mask)

        output = BytesIO()
        base.save(output, format="PNG")
        output.seek(0)
        return output
    except Exception as error:
        print(f"تعذر إنشاء صورة ترحيب للعضو {member}: {error}", flush=True)
        return None


@bot.event
async def on_member_join(member: discord.Member):
    channel = get_welcome_channel(member.guild)
    if channel is None:
        print(
            f"لم أجد شاتًا مناسبًا للترحيب في السيرفر: {member.guild.name}",
            flush=True,
        )
        return

    welcome_message = (
        f"مرحبا بك في سيرفر نيون {member.mention}\n"
        f"عددنا الآن بفضلك {member.guild.member_count}"
    )

    files = []
    welcome_image = await create_welcome_image(member)

    if welcome_image is not None:
        files.append(
            discord.File(
                welcome_image,
                filename=WELCOME_ATTACHMENT_NAME,
            )
        )

    try:
        await channel.send(content=welcome_message, files=files)
    except discord.Forbidden:
        print(
            f"لا أستطيع إرسال رسالة الترحيب في الشات: {channel.name}",
            flush=True,
        )


@bot.event
async def on_ready():
    # نسجل الـ View من جديد عند كل تشغيل حتى تستمر القائمة تشتغل
    # على الرسالة القديمة حتى لو البوت سوى Restart
    bot.add_view(ColorView())
    print(f"تم الاتصال. عدد السيرفرات: {len(bot.guilds)}", flush=True)
    if bot.user:
        print(
            "رابط الدعوة مع صلاحيات البوت وأوامر السلاش: "
            f"https://discord.com/oauth2/authorize?client_id={bot.user.id}"
            "&scope=bot%20applications.commands&permissions=268438544",
            flush=True,
        )
    for guild in bot.guilds:
        print(f"- السيرفر: {guild.name} ({guild.id})", flush=True)

    try:
        # المزامنة العامة قد تتأخر حتى ساعة. نزامن مع كل سيرفر مباشرة
        # حتى يظهر أمر /setup_colors فوراً بعد تشغيل البوت.
        total_synced = 0
        for guild in bot.guilds:
            bot.tree.copy_global_to(guild=guild)
            print(f"جارٍ تسجيل الأمر مع: {guild.name}", flush=True)
            synced = await asyncio.wait_for(
                bot.tree.sync(guild=guild),
                timeout=20,
            )
            total_synced += len(synced)
            print(
                f"تمت مزامنة {len(synced)} أمر سلاش مع السيرفر: {guild.name}",
                flush=True,
            )

        # نحذف النسخ العامة القديمة حتى لا يظهر نفس الأمر مرتين في Discord.
        # تبقى النسخة الخاصة بالسيرفرات فقط، وتظهر فوراً.
        bot.tree.clear_commands(guild=None)
        await asyncio.wait_for(bot.tree.sync(), timeout=20)
        print("تم حذف النسخ العامة القديمة من أوامر السلاش.", flush=True)
        print(f"تمت مزامنة {total_synced} أمر سلاش مع السيرفرات.", flush=True)
    except asyncio.TimeoutError:
        print(
            "انتهت مهلة تسجيل أمر السلاش. غالباً يحتاج البوت إلى إعادة دعوة "
            "بصلاحية applications.commands.",
            flush=True,
        )
    except Exception as e:
        print(f"خطأ بالمزامنة: {type(e).__name__}: {e}", flush=True)
    print(f"البوت جاهز: {bot.user}", flush=True)


@bot.tree.command(
    name="setup_colors",
    description="ينشر رسالة ثابتة في الروم فيها قائمة اختيار الألوان (مرة وحدة فقط)",
)
@app_commands.checks.has_permissions(manage_roles=True)
async def setup_colors(interaction: discord.Interaction):
    embed = discord.Embed(
        title="قم بأختيار الرتب الخاصة بك",
        description="قم بأختيار الرتب التي تناسبك من قائمة الاختيارات تحت.",
        color=discord.Color.from_rgb(147, 112, 219),
    )
    embed.set_footer(text="عمكم بلاك")

    files = []
    if os.path.exists(BANNER_IMAGE_PATH):
        banner_file = discord.File(BANNER_IMAGE_PATH, filename=BANNER_ATTACHMENT_NAME)
        files.append(banner_file)
        embed.set_image(url=f"attachment://{BANNER_ATTACHMENT_NAME}")

    if os.path.exists(THUMBNAIL_IMAGE_PATH):
        thumbnail_file = discord.File(
            THUMBNAIL_IMAGE_PATH,
            filename=THUMBNAIL_ATTACHMENT_NAME,
        )
        files.append(thumbnail_file)
        embed.set_thumbnail(url=f"attachment://{THUMBNAIL_ATTACHMENT_NAME}")

    if interaction.channel is None:
        await interaction.response.send_message(
            "❌ ما قدرت أحدد الروم لإرسال قائمة الألوان.",
            ephemeral=True,
        )
        return

    await interaction.channel.send(embed=embed, files=files, view=ColorView())
    await interaction.response.send_message("✅ تم نشر قائمة الألوان في الروم.", ephemeral=True)


@setup_colors.error
async def setup_colors_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "❌ لازم تكون عندك صلاحية Manage Roles حتى تسوي هذا الأمر.",
            ephemeral=True,
        )
    else:
        raise error


@bot.tree.command(
    name="setup_welcome",
    description="يحدد الشات الذي تصل فيه رسائل الترحيب",
)
@app_commands.describe(channel="اختر شات الترحيب")
@app_commands.checks.has_permissions(manage_guild=True)
async def setup_welcome(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
):
    if interaction.guild is None:
        await send_command_error(interaction, "هذا الأمر يعمل داخل السيرفر فقط.")
        return

    WELCOME_CHANNELS[str(interaction.guild.id)] = channel.id
    save_welcome_channels()
    await interaction.response.send_message(
        f"✅ تم تحديد {channel.mention} كشات الترحيب.",
        ephemeral=True,
    )


@bot.tree.command(
    name="line",
    description="يرسل صورة الخط في الشات الذي تختاره",
)
@app_commands.describe(channel="اختر الشات الذي تريد إرسال صورة الخط فيه")
async def line(interaction: discord.Interaction, channel: discord.TextChannel):
    if not os.path.exists(BORDER_IMAGE_PATH):
        await interaction.response.send_message(
            "❌ صورة الخط غير موجودة.",
            ephemeral=True,
        )
        return

    line_file = discord.File(
        BORDER_IMAGE_PATH,
        filename=BORDER_ATTACHMENT_NAME,
    )
    try:
        await channel.send(file=line_file)
        await interaction.response.send_message(
            f"✅ تم إرسال صورة الخط في {channel.mention}.",
            ephemeral=True,
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            f"❌ ما أقدر أرسل في {channel.mention}. تأكد أن للبوت صلاحية "
            "Send Messages و Attach Files في هذا الشات.",
            ephemeral=True,
        )


@bot.tree.command(name="ping", description="يعرض سرعة استجابة البوت")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(
        f"سرعة استجابة البوت: **{latency}ms**",
        ephemeral=True,
    )


@bot.tree.command(name="help", description="يعرض جميع أوامر البوت")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="أوامر بوت Neon",
        description="هذه الأوامر المتاحة في البوت:",
        color=discord.Color.from_rgb(147, 112, 219),
    )
    embed.add_field(
        name="عام",
        value=(
            "`/ping` سرعة البوت\n"
            "`/serverinfo` معلومات السيرفر\n"
            "`/userinfo` معلومات عضو\n"
            "`/avatar` صورة عضو\n"
            "`/color_list` قائمة الألوان\n"
            "`/roleinfo` معلومات رول"
        ),
        inline=False,
    )
    embed.add_field(
        name="إدارة",
        value=(
            "`/clear` حذف رسائل\n"
            "`/lock` قفل شات\n"
            "`/unlock` فتح شات\n"
            "`/slowmode` تفعيل التهدئة\n"
            "`/announce` إرسال إعلان\n"
            "`/rules` إرسال القوانين\n"
             "`/socials` عرض الروابط\n"
             "`/setup_welcome` تحديد شات الترحيب"
        ),
        inline=False,
    )
    embed.add_field(
        name="الرولات والمجتمع",
        value=(
            "`/set_color` إعطاء لون لعضو\n"
            "`/remove_color` إزالة لون عضو\n"
            "`/suggest` إرسال اقتراح\n"
            "`/report` رفع بلاغ\n"
            "`/poll` إنشاء تصويت"
        ),
        inline=False,
    )
    embed.set_footer(text="عمكم بلاك")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="serverinfo", description="يعرض معلومات السيرفر")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    if guild is None:
        await send_command_error(interaction, "هذا الأمر يعمل داخل السيرفر فقط.")
        return

    embed = discord.Embed(
        title=f"معلومات {guild.name}",
        color=discord.Color.from_rgb(147, 112, 219),
    )
    embed.add_field(name="المالك", value=f"<@{guild.owner_id}>", inline=True)
    embed.add_field(name="عدد الأعضاء", value=str(guild.member_count), inline=True)
    embed.add_field(name="عدد الرولات", value=str(len(guild.roles) - 1), inline=True)
    embed.add_field(name="عدد الشاتات", value=str(len(guild.channels)), inline=True)
    embed.add_field(name="معرّف السيرفر", value=str(guild.id), inline=True)
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="userinfo", description="يعرض معلومات عضو")
@app_commands.describe(member="اختر العضو")
async def userinfo(
    interaction: discord.Interaction,
    member: discord.Member | None = None,
):
    selected_member = member or interaction.user
    embed = discord.Embed(
        title=f"معلومات {selected_member.display_name}",
        color=selected_member.color
        if selected_member.color != discord.Color.default()
        else discord.Color.from_rgb(147, 112, 219),
    )
    embed.add_field(name="الاسم", value=str(selected_member), inline=True)
    embed.add_field(name="معرّف العضو", value=str(selected_member.id), inline=True)
    embed.add_field(
        name="تاريخ الانضمام",
        value=discord.utils.format_dt(selected_member.joined_at, "D")
        if selected_member.joined_at
        else "غير معروف",
        inline=False,
    )
    embed.add_field(
        name="الرولات",
        value=", ".join(role.mention for role in selected_member.roles[1:]) or "لا يوجد",
        inline=False,
    )
    embed.set_thumbnail(url=selected_member.display_avatar.url)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="avatar", description="يعرض صورة عضو")
@app_commands.describe(member="اختر العضو")
async def avatar(
    interaction: discord.Interaction,
    member: discord.Member | None = None,
):
    selected_member = member or interaction.user
    embed = discord.Embed(
        title=f"صورة {selected_member.display_name}",
        color=discord.Color.from_rgb(147, 112, 219),
    )
    embed.set_image(url=selected_member.display_avatar.url)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="clear", description="يحذف عددًا من الرسائل")
@app_commands.describe(amount="عدد الرسائل من 1 إلى 100")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(
    interaction: discord.Interaction,
    amount: app_commands.Range[int, 1, 100],
):
    if not isinstance(interaction.channel, discord.TextChannel):
        await send_command_error(interaction, "هذا الأمر يعمل في الشاتات النصية فقط.")
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(
        f"تم حذف **{len(deleted)}** رسالة.",
        ephemeral=True,
    )


@bot.tree.command(name="lock", description="يقفل شاتًا ويمنع الأعضاء من الكتابة")
@app_commands.describe(channel="الشات المطلوب قفله، اتركه فارغًا للشات الحالي")
@app_commands.checks.has_permissions(manage_channels=True)
async def lock(
    interaction: discord.Interaction,
    channel: discord.TextChannel | None = None,
):
    target = channel or interaction.channel
    if not isinstance(target, discord.TextChannel) or interaction.guild is None:
        await send_command_error(interaction, "هذا الأمر يعمل على شات نصي داخل السيرفر.")
        return
    overwrite = target.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = False
    await target.set_permissions(
        interaction.guild.default_role,
        overwrite=overwrite,
        reason=f"قفل بواسطة {interaction.user}",
    )
    await interaction.response.send_message(f"تم قفل {target.mention}.")


@bot.tree.command(name="unlock", description="يفتح شاتًا ويسمح للأعضاء بالكتابة")
@app_commands.describe(channel="الشات المطلوب فتحه، اتركه فارغًا للشات الحالي")
@app_commands.checks.has_permissions(manage_channels=True)
async def unlock(
    interaction: discord.Interaction,
    channel: discord.TextChannel | None = None,
):
    target = channel or interaction.channel
    if not isinstance(target, discord.TextChannel) or interaction.guild is None:
        await send_command_error(interaction, "هذا الأمر يعمل على شات نصي داخل السيرفر.")
        return
    overwrite = target.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = None
    await target.set_permissions(
        interaction.guild.default_role,
        overwrite=overwrite,
        reason=f"فتح بواسطة {interaction.user}",
    )
    await interaction.response.send_message(f"تم فتح {target.mention}.")


@bot.tree.command(name="slowmode", description="يضبط التهدئة في شات")
@app_commands.describe(
    seconds="المدة بالثواني من 0 إلى 21600",
    channel="الشات المطلوب، اتركه فارغًا للشات الحالي",
)
@app_commands.checks.has_permissions(manage_channels=True)
async def slowmode(
    interaction: discord.Interaction,
    seconds: app_commands.Range[int, 0, 21600],
    channel: discord.TextChannel | None = None,
):
    target = channel or interaction.channel
    if not isinstance(target, discord.TextChannel):
        await send_command_error(interaction, "هذا الأمر يعمل على شات نصي فقط.")
        return
    await target.edit(
        slowmode_delay=seconds,
        reason=f"تعديل التهدئة بواسطة {interaction.user}",
    )
    status = "تم إيقاف التهدئة" if seconds == 0 else f"تم ضبط التهدئة على {seconds} ثانية"
    await interaction.response.send_message(f"{status} في {target.mention}.")


@bot.tree.command(name="announce", description="يرسل إعلانًا في شات تختاره")
@app_commands.describe(
    channel="شات الإعلان",
    message="نص الإعلان",
)
@app_commands.checks.has_permissions(manage_messages=True)
async def announce(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    message: str,
):
    embed = discord.Embed(
        title="إعلان",
        description=message,
        color=discord.Color.from_rgb(147, 112, 219),
    )
    embed.set_footer(text=f"بواسطة {interaction.user.display_name}")
    try:
        await channel.send(embed=embed)
        await interaction.response.send_message(
            f"تم إرسال الإعلان في {channel.mention}.",
            ephemeral=True,
        )
    except discord.Forbidden:
        await send_command_error(
            interaction,
            "ما عندي صلاحية الإرسال في الشات المحدد.",
        )


@bot.tree.command(name="remove_color", description="يزيل رول اللون من عضو")
@app_commands.describe(member="اختر العضو")
@app_commands.checks.has_permissions(manage_roles=True)
async def remove_color(interaction: discord.Interaction, member: discord.Member):
    roles_to_remove = [role for role in member.roles if role.id in ALL_COLOR_ROLE_IDS]
    if not roles_to_remove:
        await interaction.response.send_message(
            f"العضو {member.mention} لا يملك رول لون.",
            ephemeral=True,
        )
        return
    try:
        await member.remove_roles(*roles_to_remove, reason=f"إزالة لون بواسطة {interaction.user}")
        await interaction.response.send_message(
            f"تمت إزالة رول اللون من {member.mention}.",
            ephemeral=True,
        )
    except discord.Forbidden:
        await send_command_error(interaction, "لا أستطيع إزالة الرول بسبب ترتيب الرولات أو الصلاحيات.")


@bot.tree.command(name="set_color", description="يعطي رول لون لعضو")
@app_commands.describe(member="اختر العضو", color="اختر اللون")
@app_commands.choices(color=COLOR_CHOICES)
@app_commands.checks.has_permissions(manage_roles=True)
async def set_color(
    interaction: discord.Interaction,
    member: discord.Member,
    color: app_commands.Choice[str],
):
    role = get_color_role(interaction.guild, color.value) if interaction.guild else None
    if role is None:
        await send_command_error(interaction, "الرول غير موجود في هذا السيرفر.")
        return
    if not role.is_assignable():
        await send_command_error(interaction, "لا أستطيع إعطاء هذا الرول. ارفع رتبة البوت فوقه.")
        return
    roles_to_remove = [item for item in member.roles if item.id in ALL_COLOR_ROLE_IDS]
    try:
        if roles_to_remove:
            await member.remove_roles(*roles_to_remove, reason=f"تبديل لون بواسطة {interaction.user}")
        await member.add_roles(role, reason=f"إعطاء لون بواسطة {interaction.user}")
        await interaction.response.send_message(
            f"تم إعطاء {member.mention} رول **{role.name}**.",
            ephemeral=True,
        )
    except discord.Forbidden:
        await send_command_error(interaction, "لا أستطيع تعديل رولات العضو.")


@bot.tree.command(name="color_list", description="يعرض رولات الألوان المتاحة")
async def color_list(interaction: discord.Interaction):
    guild = interaction.guild
    if guild is None:
        await send_command_error(interaction, "هذا الأمر يعمل داخل السيرفر فقط.")
        return
    values = []
    for name, role_id in COLOR_ROLES:
        role = guild.get_role(role_id)
        values.append(f"**{name}** — {role.mention if role else 'غير موجود'}")
    embed = discord.Embed(
        title="رولات الألوان",
        description="\n".join(values),
        color=discord.Color.from_rgb(147, 112, 219),
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="roleinfo", description="يعرض معلومات رول")
@app_commands.describe(role="اختر الرول")
async def roleinfo(interaction: discord.Interaction, role: discord.Role):
    embed = discord.Embed(
        title=f"معلومات رول {role.name}",
        color=role.color if role.color != discord.Color.default() else discord.Color.from_rgb(147, 112, 219),
    )
    embed.add_field(name="المعرّف", value=str(role.id), inline=True)
    embed.add_field(name="الترتيب", value=str(role.position), inline=True)
    embed.add_field(name="عدد الأعضاء", value=str(len(role.members)), inline=True)
    embed.add_field(name="قابل للمنشن", value="نعم" if role.mentionable else "لا", inline=True)
    embed.add_field(name="يديره البوت", value="نعم" if role.is_bot_managed() else "لا", inline=True)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="suggest", description="يرسل اقتراحًا في الشات")
@app_commands.describe(suggestion="اكتب اقتراحك")
async def suggest(interaction: discord.Interaction, suggestion: str):
    if interaction.channel is None:
        await send_command_error(interaction, "لا يمكن تحديد الشات.")
        return
    embed = discord.Embed(
        title="اقتراح جديد",
        description=suggestion,
        color=discord.Color.from_rgb(147, 112, 219),
    )
    embed.set_author(
        name=interaction.user.display_name,
        icon_url=interaction.user.display_avatar.url,
    )
    message = await interaction.channel.send(embed=embed)
    await message.add_reaction("👍")
    await message.add_reaction("👎")
    await interaction.response.send_message("تم إرسال اقتراحك.", ephemeral=True)


@bot.tree.command(name="report", description="يرسل بلاغًا عن عضو")
@app_commands.describe(member="العضو المبلغ عنه", reason="سبب البلاغ")
async def report(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str,
):
    if interaction.channel is None:
        await send_command_error(interaction, "لا يمكن تحديد الشات.")
        return
    embed = discord.Embed(
        title="بلاغ جديد",
        color=discord.Color.red(),
    )
    embed.add_field(name="المبلّغ", value=interaction.user.mention, inline=True)
    embed.add_field(name="العضو", value=member.mention, inline=True)
    embed.add_field(name="السبب", value=reason, inline=False)
    await interaction.channel.send(embed=embed)
    await interaction.response.send_message("تم إرسال البلاغ للإدارة.", ephemeral=True)


@bot.tree.command(name="poll", description="ينشئ تصويتًا بنعم أو لا")
@app_commands.describe(question="اكتب سؤال التصويت")
async def poll(interaction: discord.Interaction, question: str):
    if interaction.channel is None:
        await send_command_error(interaction, "لا يمكن تحديد الشات.")
        return
    embed = discord.Embed(
        title="تصويت",
        description=question,
        color=discord.Color.from_rgb(147, 112, 219),
    )
    embed.set_footer(text=f"بواسطة {interaction.user.display_name}")
    message = await interaction.channel.send(embed=embed)
    await message.add_reaction("👍")
    await message.add_reaction("👎")
    await interaction.response.send_message("تم إنشاء التصويت.", ephemeral=True)


@bot.tree.command(name="rules", description="يرسل قوانين السيرفر")
@app_commands.checks.has_permissions(manage_guild=True)
async def rules(interaction: discord.Interaction):
    if interaction.channel is None:
        await send_command_error(interaction, "لا يمكن تحديد الشات.")
        return
    embed = discord.Embed(
        title="قوانين السيرفر",
        description=(
            "احترم جميع الأعضاء.\n"
            "يمنع الإزعاج والسبام.\n"
            "يمنع نشر الإعلانات دون إذن الإدارة.\n"
            "اتبع تعليمات الإدارة."
        ),
        color=discord.Color.from_rgb(147, 112, 219),
    )
    embed.set_footer(text="عمكم بلاك")
    await interaction.channel.send(embed=embed)
    await interaction.response.send_message("تم إرسال القوانين.", ephemeral=True)


@bot.tree.command(name="socials", description="يعرض روابط السيرفر")
async def socials(interaction: discord.Interaction):
    if not SOCIAL_LINKS:
        await interaction.response.send_message(
            "لم تتم إضافة روابط التواصل بعد. أضفها في قائمة SOCIAL_LINKS داخل ملف البوت.",
            ephemeral=True,
        )
        return
    embed = discord.Embed(
        title="روابط Neon",
        description="\n".join(SOCIAL_LINKS),
        color=discord.Color.from_rgb(147, 112, 219),
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
):
    if isinstance(error, app_commands.MissingPermissions):
        await send_command_error(interaction, "ما عندك الصلاحية اللازمة لاستخدام هذا الأمر.")
    elif isinstance(error, app_commands.CommandInvokeError) and isinstance(
        error.original,
        discord.Forbidden,
    ):
        await send_command_error(interaction, "البوت لا يملك الصلاحية اللازمة لهذا الأمر.")
    else:
        print(f"خطأ في أمر سلاش: {type(error).__name__}: {error}", flush=True)
        await send_command_error(interaction, "حدث خطأ أثناء تنفيذ الأمر.")


if __name__ == "__main__":
    if TOKEN == "ضع_التوكن_هنا":
        print("⚠️ حط التوكن الخاص بالبوت في متغير البيئة DISCORD_TOKEN أو داخل الكود.")
    bot.run(TOKEN)
