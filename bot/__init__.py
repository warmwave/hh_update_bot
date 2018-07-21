from typing import Optional, Dict, List, Any
import os
import re
import logging
import random
import asyncio
import aiopg
import telepot
import telepot.aio
from hh_api import HeadHunterAPI, HeadHunterResume, HeadHunterAuthError
from telepot.aio.loop import MessageLoop

# logging
log = logging.getLogger('hh-update-bot')
log.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

ch = logging.StreamHandler()
ch.setFormatter(formatter)
log.addHandler(ch)

pg_pool = None
token_pattern = re.compile(r"^[A-Z0-9]{64}$")


incorrect_message_answers = [
    'Извини, не понимаю. Отправь /help, чтобы увидеть полный список моих команд.',
    'Сложно, не понятно. Отправь /help, чтобы увидеть полный список моих команд.',
    'Я не знаю такой команды. Отправь /help, чтобы увидеть полный список моих команд.',
]

hello_message = ('Привет! Я регулярно (примерно раз в четыре часа) буду поднимать твоё резюме в поиске на hh.ru, '
                 'чтобы его увидело большее количество работодателей. '
                 'И тебе даже не придется платить за это ни рубля! :)\n\n'
                 
                 '<b>Важное замечание</b>\n'
                 'Наверняка ребята из hh.ru не обрадуются, что я предоставляю такие услуги бесплатно, '
                 'ведь они берут за это деньги '
                 '(см. цены <a href="https://hh.ru/applicant/resume_service/renewresume">здесь</a>). '
                 'Поэтому я не могу просто создать "приложение", использующее API hh.ru — его заблокируют. '
                 'Но при этом hh.ru открыто предоставляет пользователям API и не запрещает писать скрипты для '
                 'любых своих целей, которые не противоречат правилам. Поэтому мне нужен твой авторизационный токен, '
                 'чтобы производить обновление резюме от твоего лица. '
                 'Я, конечно, буду использовать этот токен ТОЛЬКО для поднятия твоих резюме в поиске, '
                 'честно-честно, но ты должен понимать, что вообще-то передавать свой авторизационный токен '
                 'третьим лицам — небезопасно. Помни, что ты используешь этого бота на свой страх и риск. '
                 'Кстати, токен в любой момент можно отозвать, нажав на иконку "корзины" напротив токена на hh.ru, '
                 'и я настоятельно рекомендую тебе так и поступить, как только мои услуги станут тебе не нужны. '
                 'Кроме того, мой исходный код (на Python) ты всегда можешь посмотреть здесь: '
                 'https://github.com/BrokeRU/hh_update_bot.\n\n'
                 
                 'Итак, план действий следующий:\n'
                 '1. Авторизоваться на hh.ru;\n'
                 '2. Перейти по ссылке: https://dev.hh.ru/admin;\n'
                 '3. Нажать кнопку "Запросить токен";\n'
                 '4. Скопировать <code>access_token</code> (64 символа) и отправить мне.\n\n'
                 )
help_message = ('/start — приветственное сообщение;\n'
                '/help — список доступных команд;\n'
                '/token — сменить токен для доступа к hh.ru;\n'
                '/cancel — отменить ввод токена;\n'
                '/resumes — получить список доступных резюме;\n'
                '/active — получить список продвигаемых резюме.'
                )
new_token_message = ('Отправь мне токен для доступа к hh.ru. Напоминаю, что токен можно взять отсюда: '
                     'https://dev.hh.ru/admin. Если передумал, то отправь /cancel.')
new_token_cancel_message = 'Установка нового токена отменена.'
token_incorrect_message = 'Неправильный токен. Ты уверен, что скопировал всё правильно?'
no_resumes_available_message = 'Нет ни одного резюме! Добавь резюме (а лучше несколько) на hh.ru и попробуй снова.'
select_resume_message = 'Выбери одно или несколько резюме, которые будем продвигать в поиске.\n\n'
resume_selected_message = ('Ок, резюме <b>"{title}"</b> будет регулярно подниматься в поиске каждые четыре часа в '
                           'течение одной недели. Через неделю тебе нужно будет написать мне, '
                           'чтобы продолжить поднимать резюме. Я предупрежу тебя. Желаю найти работу мечты!')
active_resumes_message = 'Продвигаемые резюме:\n\n'


async def send_message(chat_id, message):
    await bot.sendMessage(chat_id, message, parse_mode='HTML')


async def on_unknown_message(chat_id):
    msg = random.choice(incorrect_message_answers)
    await send_message(chat_id, msg)


async def on_chat_message(msg):
    content_type, chat_type, user_id = telepot.glance(msg)
    log.info(f"Chat: {content_type}, {chat_type}, {user_id}")
    log.info(msg)

    # answer in private chats only
    if chat_type != 'private':
        return

    # answer for text messages only
    if content_type != 'text':
        return await on_unknown_message(user_id)

    # check if user is new
    user = await get_user(int(user_id))

    # unknown user
    if not user:
        log.info(f'Unknown user: {user_id}')
        await create_user(int(user_id))
        await send_message(user_id, hello_message)
        return

    # known user
    log.info(f'Known user: {user_id}')

    command = msg['text'].lower()

    if command == '/start':
        await send_message(user_id, hello_message)
    elif command == '/help':
        await send_message(user_id, help_message)
    elif command == '/token':
        # wait for token
        user['is_waiting_for_token'] = True
        await update_user(user)
        await send_message(user_id, new_token_message)
    elif command == '/cancel':
        # cancel waiting for token
        user['is_waiting_for_token'] = False
        await update_user(user)
        await send_message(user_id, new_token_cancel_message)
    elif command == '/resumes':
        await get_resume_list(user)
    elif command == '/active':
        await get_active_resume_list(user)
    elif command.startswith('/resume_'):
        resume_id = command.split('_')[1]
        await activate_resume(user, resume_id)
    elif user['is_waiting_for_token']:
        token = msg['text'].upper()
        await save_token(user, token)
    else:
        await on_unknown_message(user_id)


async def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    async with pg_pool.acquire() as conn:
        async with conn.cursor() as cur:
            log.info(f'Getting user with id {user_id}...')
            await cur.execute(
                """
                SELECT * FROM public.user WHERE user_id = %(user_id)s;
                """,
                {'user_id': user_id}
            )
            user = await cur.fetchone()
            if not user:
                return None
            return {
                'user_id': user[0],
                'hh_token': user[1],
                'first_name': user[2],
                'last_name': user[3],
                'email': user[4],
                'is_waiting_for_token': user[5]
            }


async def create_user(user_id: int) -> None:
    async with pg_pool.acquire() as conn:
        async with conn.cursor() as cur:
            log.info(f'Creating user with id {user_id}...')
            await cur.execute(
                """
                INSERT INTO public.user (user_id) VALUES (%(user_id)s);
                """,
                {'user_id': user_id}
            )


async def update_user(user: Dict[str, Any]) -> None:
    assert 'user_id' in user
    assert 'hh_token' in user
    assert 'first_name' in user
    assert 'last_name' in user
    assert 'email' in user
    assert 'is_waiting_for_token' in user

    async with pg_pool.acquire() as conn:
        async with conn.cursor() as cur:
            log.info(f"Updating user with id {user['user_id']}...")

            await cur.execute(
                """
                UPDATE
                    public.user
                SET
                    hh_token=%(hh_token)s,
                    first_name=%(first_name)s,
                    last_name=%(last_name)s,
                    email=%(email)s,
                    is_waiting_for_token=%(is_waiting_for_token)s
                WHERE
                    user_id=%(user_id)s;
                """,
                {
                    **user
                }
            )


async def activate_resume(user: Dict[str, Any], resume_id: str) -> None:
    assert 'user_id' in user
    assert 'hh_token' in user

    user_id = user['user_id']
    hh_token = user['hh_token']

    resume: HeadHunterResume

    try:
        async with await HeadHunterAPI.create(hh_token) as api:
            resume = await api.get_resume(resume_id)
    except HeadHunterAuthError:
        await send_message(user_id, token_incorrect_message)

    await insert_or_update_resume(user, resume)
    await send_message(user_id, resume_selected_message.format(title=resume.title))


async def insert_or_update_resume(user: Dict[str, Any], resume: HeadHunterResume) -> None:
    assert 'user_id' in user
    assert resume.id
    assert resume.title
    assert resume.next_publish_at

    log.info(f"Insert or update resume: {resume.id}, user: {user['user_id']}")

    async with pg_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE
                    public.resume
                SET
                    user_id=%(user_id)s,
                    title=%(title)s,
                    status=%(status)s,
                    next_publish_at=%(next_publish_at)s,
                    access=%(access)s,
                    until=NOW() + interval '1 week',
                    is_owner_notified=false
                WHERE resume_id=%(resume_id)s;
                
                INSERT INTO
                    public.resume
                    (resume_id, user_id, title, status, next_publish_at, access, until, is_owner_notified)
                    SELECT
                        %(resume_id)s,
                        %(user_id)s,
                        %(title)s,
                        %(status)s,
                        %(next_publish_at)s,
                        %(access)s,
                        NOW() + interval '1 week',
                        false
                    WHERE NOT EXISTS (
                        SELECT
                            1
                        FROM
                            public.resume
                        WHERE
                            resume_id=%(resume_id)s
                    );
                """,
                {
                    'resume_id': resume.id,
                    'user_id': user['user_id'],
                    'title': resume.title,
                    'status': resume.status,
                    'next_publish_at': resume.next_publish_at,
                    'access': resume.access
                }
            )


async def get_active_resume_list(user: Dict[str, Any]) -> None:
    assert 'user_id' in user

    user_id = user['user_id']

    active_resumes = await pg_get_active_resume_list(user)

    msg = active_resumes_message
    msg += '\n\n'.join(f'<b>{r.title}</b>\n/deactivate_{r.id}' for r in active_resumes)

    await send_message(user_id, msg)


async def pg_get_active_resume_list(user: Dict[str, Any]) -> List[HeadHunterResume]:
    assert 'user_id' in user

    async with pg_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT
                    resume_id, title, status, next_publish_at, access
                FROM
                    public.resume
                WHERE
                    user_id=%(user_id)s AND
                    until > NOW();
                """,
                {
                    'user_id': user['user_id']
                }
            )

            resumes = await cur.fetchall()
            return [
                HeadHunterResume(
                    id=r[0],
                    title=r[1],
                    status=r[2],
                    next_publish_at=r[3],
                    access=r[4]
                )
                for r in resumes
            ]


async def save_token(user: Dict[str, Any], hh_token: str) -> None:
    assert 'user_id' in user

    user_id = user['user_id']

    if not token_pattern.match(hh_token):
        # token mismatched pattern
        log.info(f'Token for chat {user_id} NOT matched pattern: {hh_token}')
        await send_message(user_id, token_incorrect_message)
        return

    log.info(f'Token for chat {user_id} matched pattern.')

    # create API object
    try:
        async with await HeadHunterAPI.create(hh_token) as api:
            # update user object
            user['hh_token'] = hh_token
            user['is_waiting_for_token'] = False
            user['first_name'] = api.first_name
            user['last_name'] = api.last_name
            user['email'] = api.email
            await update_user(user)
    except HeadHunterAuthError:
        await send_message(user_id, token_incorrect_message)
        return

    await get_resume_list(user)


async def get_resume_list(user: Dict[str, Any]) -> None:
    assert 'user_id' in user
    assert 'hh_token' in user

    user_id = user['user_id']
    hh_token = user['hh_token']

    log.info(f'Get resume list for user: {user_id}, token: {hh_token}')

    try:
        async with await HeadHunterAPI.create(hh_token) as api:
            # get resume list
            resumes: List[HeadHunterResume] = await api.get_resume_list()

            if resumes:
                msg = select_resume_message
                msg += '\n\n'.join(f'<b>{r.title}</b>\n/resume_{r.id}' for r in resumes)
                await send_message(user_id, msg)
            else:
                # no available resumes
                await send_message(user_id, no_resumes_available_message)
    except HeadHunterAuthError:
        await send_message(user_id, token_incorrect_message)
        return


async def postgres_connect() -> None:
    global pg_pool

    log.info("Connecting to PostgreSQL...")

    # get environment variables
    PG_HOST: str = os.environ['POSTGRES_HOST']
    PG_PORT: str = os.environ['POSTGRES_PORT']
    PG_DB: str = os.environ['POSTGRES_DB']
    PG_USER: str = os.environ['POSTGRES_USER']
    PG_PASSWORD: str = os.environ['POSTGRES_PASSWORD']

    # see: https://www.postgresql.org/docs/current/static/libpq-connect.html#LIBPQ-CONNSTRING
    dsn: str = f'dbname={PG_DB} user={PG_USER} password={PG_PASSWORD} host={PG_HOST} port={PG_PORT}'

    pg_pool = await aiopg.create_pool(dsn)


async def postgres_create_tables() -> None:
    async with pg_pool.acquire() as conn:
        async with conn.cursor() as cur:
            log.info("Creating tables...")
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS public."user"
                (
                    user_id bigint NOT NULL,
                    hh_token character varying(64) COLLATE pg_catalog."default",
                    first_name character varying(64) COLLATE pg_catalog."default",
                    last_name character varying(64) COLLATE pg_catalog."default",
                    email character varying(64) COLLATE pg_catalog."default",
                    is_waiting_for_token boolean NOT NULL DEFAULT true,
                    CONSTRAINT user_pkey PRIMARY KEY (user_id)
                )
                WITH (
                    OIDS = FALSE
                )
                TABLESPACE pg_default;
                
                ALTER TABLE public."user"
                    OWNER to postgres;
    
    
    
                CREATE TABLE IF NOT EXISTS public.resume
                (
                    resume_id character varying(64) COLLATE pg_catalog."default" NOT NULL,
                    user_id bigint NOT NULL,
                    title character varying(128) COLLATE pg_catalog."default" NOT NULL,
                    status character varying(64) COLLATE pg_catalog."default" NOT NULL,
                    next_publish_at timestamp with time zone NOT NULL,
                    access character varying(64) COLLATE pg_catalog."default" NOT NULL,
                    until timestamp with time zone NOT NULL,
                    is_owner_notified boolean NOT NULL DEFAULT false,
                    CONSTRAINT resume_pkey PRIMARY KEY (resume_id),
                    CONSTRAINT fk_resume_user_id FOREIGN KEY (user_id)
                        REFERENCES public."user" (user_id) MATCH SIMPLE
                        ON UPDATE NO ACTION
                        ON DELETE CASCADE
                )
                WITH (
                    OIDS = FALSE
                )
                TABLESPACE pg_default;
                
                ALTER TABLE public.resume
                    OWNER to postgres;
                """
            )


if __name__ == '__main__':
    # get environment variables
    TOKEN: str = os.environ['BOT_TOKEN']

    bot: telepot.aio.Bot = telepot.aio.Bot(TOKEN)
    answerer: telepot.aio.helper.Answerer = telepot.aio.helper.Answerer(bot)

    loop = asyncio.get_event_loop()

    loop.run_until_complete(postgres_connect())
    loop.run_until_complete(postgres_create_tables())

    loop.create_task(MessageLoop(bot, {'chat': on_chat_message}).run_forever())

    log.info('Listening for messages in Telegram...')

    loop.run_forever()
