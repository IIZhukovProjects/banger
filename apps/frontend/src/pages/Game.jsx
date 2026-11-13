import React, { useEffect, useState } from "react";
import { ArrowRight, Check, Crown, Sparkles, RotateCcw } from "lucide-react";
import "../styles/style.css";
import Lobby from "../components/Lobby";
import "../styles/lobby.css";
import RoomHub from "../components/RoomHub";
import GameSetup from "../components/GameSetup";
import "../styles/rooms.css";
const isTV = location.pathname.startsWith("/tv");
const requestedRoom = (new URLSearchParams(location.search).get("room") || "")
  .trim()
  .toUpperCase();
const roomCode = requestedRoom
  ? /^[A-Z0-9]{6}$/.test(requestedRoom)
    ? requestedRoom
    : "INVALID"
  : "";
const storageKey = "benger-player:" + roomCode;
let token = isTV
  ? ""
  : localStorage.getItem(storageKey) ||
    (roomCode === "BENGER" ? localStorage.getItem("kto-player") : "") ||
    "";
function imageSource(url) {
  return url?.startsWith("/uploads/") ? "/api" + url : url;
}
async function api(path, body, method) {
  const r = await fetch("/api/" + path, {
    method: method || (body === undefined ? "GET" : "POST"),
    headers: {
      Authorization: token,
      "Content-Type": "application/json",
      ...(roomCode && { "X-Room-Code": roomCode }),
    },
    ...(body !== undefined && { body: JSON.stringify(body) }),
  });
  const d = await r.json();
  if (!r.ok) {
    const error = Error(
      typeof d.detail === "string" ? d.detail : "Не удалось выполнить действие",
    );
    error.status = r.status;
    throw error;
  }
  return d;
}
function Sticker({ index = 0 }) {
  return (
    <span
      className="sticker"
      style={{
        backgroundPosition: `${(index % 3) * 50}% ${Math.floor(index / 3) * 50}%`,
      }}
    />
  );
}
function PartyBurst() {
  return (
    <div className="party-burst" aria-hidden="true">
      {Array.from({ length: 22 }, (_, i) => (
        <i
          key={i}
          style={{
            "--x": ((i * 37) % 100) + "%",
            "--delay": (i % 7) * 55 + "ms",
            "--spin": (i % 2 ? 1 : -1) * (i * 27 + 160) + "deg",
          }}
        >
          {["✦", "✺", "◆", "★"][i % 4]}
        </i>
      ))}
    </div>
  );
}
const answerLabel = (i) => "АБВГДЕЖЗИКЛМНОПРСТУФХЦЧШЩЭЮЯ"[i] || String(i + 1);
const PAGE_SIZE = 8;
export default function Game() {
  const [s, setS] = useState(null),
    [missingRoom, setMissingRoom] = useState(false),
    [meta, setMeta] = useState(null),
    [now, setNow] = useState(Date.now()),
    [online, setOnline] = useState(true);
  const [second, setSecond] = useState(""),
    [tvPage, setTvPage] = useState(0),
    [upload, setUpload] = useState(null);
  const [name, setName] = useState(""),
    [text, setText] = useState(""),
    [power, setPower] = useState(false),
    [pick, setPick] = useState(""),
    [block, setBlock] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [generating, setGenerating] = useState(false);
  useEffect(() => {
    let alive = true,
      loading = false;
    const loadMeta = () =>
      api("meta")
        .then((d) => {
          if (alive) setMeta(d);
        })
        .catch(() => {});
    loadMeta();
    async function poll() {
      if (loading) return;
      loading = true;
      try {
        const d = await api("state");
        if (alive) {
          setS(d);
          setOnline(true);
        }
      } catch (error) {
        if (alive) {
          setOnline(false);
          if (error.status === 404) setMissingRoom(true);
        }
      } finally {
        loading = false;
      }
    }
    poll();
    const interval = setInterval(poll, 1000),
      clock = setInterval(() => setNow(Date.now()), 500),
      catalog = setInterval(loadMeta, 10000);
    return () => {
      alive = false;
      clearInterval(interval);
      clearInterval(clock);
      clearInterval(catalog);
    };
  }, []);
  useEffect(() => {
    setText("");
    setSecond("");
    setPower(false);
    setPick("");
    setBlock("");
    setError("");
  }, [s?.round?.round_id, s?.phase]);
  async function act(path, body = {}, method) {
    setBusy(true);
    setError("");
    try {
      const d = await api(path, body, method);
      if (d.token) {
        token = d.token;
        localStorage.setItem(storageKey, token);
      }
      setS(await api("state"));
      return d;
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function leave() {
    if (await act("leave")) {
      token = "";
      localStorage.removeItem(storageKey);
      if (roomCode === "BENGER") localStorage.removeItem("kto-player");
      setS(await api("state"));
    }
  }
  async function generate() {
    setGenerating(true);
    await act("generate", { text, power, round_id: s.round.round_id });
    setGenerating(false);
  }
  const me = s?.me,
    r = s?.round,
    players = s?.players || [],
    mode = r?.mode_info || meta?.modes[r?.mode],
    isImage = s?.phase === "answer" && ["image", "relay"].includes(r?.kind),
    isRelay = r?.kind === "relay",
    isCaption = s?.phase === "caption",
    capacity = s?.capacity ?? null;
  const minimum =
    r?.kind === "relay" || s?.mode === "relay" ? 3 : meta?.min_players || 2;
  const fieldNames = meta?.answer_fields?.[r?.mode];
  const uploaded = upload?.round === r?.round_id ? upload?.url : null;
  const pageCount = Math.max(
    1,
    Math.ceil((r?.answers.length || 0) / PAGE_SIZE),
  );
  const page = Math.min(tvPage, pageCount - 1);
  const phaseKey = (r?.round_id || "room") + ":" + s?.phase;
  useEffect(() => {
    setTvPage(0);
  }, [phaseKey]);
  useEffect(() => {
    if (!isTV || pageCount < 2) return;
    const timer = setInterval(
      () => setTvPage((previous) => (previous + 1) % pageCount),
      9000,
    );
    return () => clearInterval(timer);
  }, [phaseKey, pageCount]);
  function changePage(direction) {
    setTvPage((page + direction + pageCount) % pageCount);
  }
  async function uploadClue(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const form = new FormData();
    form.set("file", file);
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/upload", {
        method: "POST",
        headers: { Authorization: token, "X-Room-Code": roomCode },
        body: form,
      });
      const data = await response.json();
      if (!response.ok)
        throw Error(
          typeof data.detail === "string"
            ? data.detail
            : "Не удалось загрузить картинку",
        );
      setUpload({ round: r.round_id, url: data.url });
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  const pendingGeneration = generating || Boolean(s?.generating);
  const seconds = Math.min(
    90,
    Math.max(0, Math.ceil(((s?.deadline || 0) * 1000 - now) / 1000)),
  );
  const nameOf = (id) => players.find((p) => p.id === id)?.name || "Игрок";
  const scores = [...players].sort((a, b) => b.score - a.score);
  const ownPoints =
    r?.answers
      .filter((a) => [a.player, a.partner].includes(me?.id))
      .reduce((sum, a) => sum + a.points, 0) || 0;
  const benger = s?.history
    .flatMap((round) => round.answers)
    .sort(
      (a, b) =>
        (b.voters?.length || 0) - (a.voters?.length || 0) ||
        b.points - a.points,
    )[0];
  const shownImage = s?.caption_image || r?.shared_image;
  const origin =
    ["localhost", "127.0.0.1"].includes(location.hostname) && meta?.lan_ip
      ? `${location.protocol}//${meta?.lan_ip}:${location.port || 80}`
      : location.origin;
  const scoreboard = (
    <div className="scoreboard">
      {scores.map((p, i) => (
        <div className="score" key={p.id}>
          <span className="rank">
            {i && scores[i - 1].score === p.score ? "=" : i + 1}
          </span>
          <b>{p.name}</b>
          <strong>
            {p.score}
            <small> б.</small>
          </strong>
        </div>
      ))}
    </div>
  );
  const continueBox = (
    <div className="continue-box">
      <span className="eyebrow">
        {s?.next_ready?.length} / {players.filter((p) => !p.waiting).length}{" "}
        ГОТОВЫ
      </span>
      {!isTV ? (
        <>
          <button
            className="primary"
            disabled={busy || s?.next_ready?.includes(me?.id)}
            onClick={() => act("next", { round_id: r.round_id })}
          >
            {s?.next_ready?.includes(me?.id) ? "Ждём остальных" : "Далее"}{" "}
            <ArrowRight size={19} />
          </button>
          {s?.is_leader && (
            <button
              className="text-button"
              disabled={busy}
              onClick={() => act("next", { round_id: r.round_id, force: true })}
            >
              Продолжить всем
            </button>
          )}
        </>
      ) : (
        <>
          <h3>Обсудили? Дальше!</h3>
          <div className="small-players">
            {players
              .filter((p) => !p.waiting)
              .map((p) => (
                <span
                  className={s?.next_ready?.includes(p.id) ? "is-ready" : ""}
                  key={p.id}
                >
                  {s?.next_ready?.includes(p.id) ? "✓ " : ""}
                  {p.name}
                </span>
              ))}
          </div>
          <p>Нажмите «Далее» на телефонах.</p>
        </>
      )}
    </div>
  );
  const ability = !isTV &&
    me &&
    !me.spent &&
    ["answer", "caption"].includes(s?.phase) &&
    !(isRelay && isImage) &&
    me.power !== "block" &&
    !s.submitted && (
      <details className="ability">
        <summary>
          {me.power_info[2]} {me.power_info[0]} <small>способность</small>
        </summary>
        <label className="ability-toggle">
          <input
            type="checkbox"
            checked={power}
            onChange={(e) => setPower(e.target.checked)}
            disabled={busy}
          />
          <span>{me.power_info[1]}</span>
        </label>
      </details>
    );
  function answers(round, revealed = false) {
    const offset = isTV ? page * PAGE_SIZE : 0;
    const visible = isTV
      ? round.answers.slice(offset, offset + PAGE_SIZE)
      : round.answers;
    return (
      <>
        <div className="answers">
          {visible.map((a, i) => (
            <article
              style={{ "--enter-delay": Math.min(i, 9) * 55 + "ms" }}
              className={
                "answer " +
                (pick === a.id ? "selected " : "") +
                (a.own ? "own" : "")
              }
              key={a.id + ":" + revealed}
            >
              <div className="answer-head">
                <b className="letter">{answerLabel(offset + i)}</b>
                {a.own && <small>Твой ответ</small>}
                {revealed && <b className="points">+{a.points}</b>}
              </div>
              {a.image && (
                <img className="answer-image" src={imageSource(a.image)} alt={a.text} />
              )}
              {fieldNames && a.text.includes("\n") ? (
                <div className="answer-lines">
                  {a.text.split("\n").map((line, j) => (
                    <div key={j}>
                      <small>{fieldNames[j]}</small>
                      <p>{line}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p>{a.text}</p>
              )}
              {revealed ? (
                <>
                  <div className="author">
                    {nameOf(a.player)}
                    {a.partner && " + " + nameOf(a.partner)}
                    {a.double && <em>×2</em>}
                    {a.bank && <em>Ва-банк ×3</em>}
                    {a.bonus && <em>Первый лайк +1</em>}
                    {a.shield && <em>Броня</em>}
                    {a.blocked && <em>Без баллов</em>}
                  </div>
                  <div className="voters">
                    {a.voters?.map((id) => (
                      <span key={id}>{nameOf(id)}</span>
                    ))}
                    {!a.voters?.length && <small>Без голосов</small>}
                  </div>
                </>
              ) : (
                !isTV &&
                !s.voted &&
                !a.own && (
                  <div className="answer-controls">
                    <button onClick={() => setPick(a.id)}>
                      {pick === a.id ? "✓ Выбрано" : "Выбрать"}
                    </button>
                    {me.power === "block" && !me.spent && (
                      <button
                        aria-label={
                          "Обнулить вариант " + answerLabel(offset + i)
                        }
                        className={block === a.id ? "danger" : ""}
                        onClick={() => setBlock(block === a.id ? "" : a.id)}
                      >
                        {block === a.id ? "∅ Обнулится" : "∅"}
                      </button>
                    )}
                  </div>
                )
              )}
            </article>
          ))}
        </div>
        {isTV && pageCount > 1 && (
          <nav className="answer-pages" aria-label="Страницы ответов">
            <button
              onClick={() => changePage(-1)}
              aria-label="Предыдущая страница"
            >
              ←
            </button>
            <span>
              {page + 1} / {pageCount}
            </span>
            <button
              onClick={() => changePage(1)}
              aria-label="Следующая страница"
            >
              →
            </button>
          </nav>
        )}
      </>
    );
  }
  function settings() {
    return (
      <>
        <section className="phone-room-actions">
          <button
            className="primary"
            disabled={busy || players.length < minimum}
            onClick={() => act("start")}
          >
            Начать игру <ArrowRight size={19} />
          </button>
          {players.length < minimum && (
            <p className="helper">Для старта нужно игроков: {minimum}.</p>
          )}
          {players.length < Math.min(capacity ?? 5, 5) && (
            <button
              className="text-button"
              disabled={busy}
              onClick={() => act("bots")}
            >
              Добавить демоигроков
            </button>
          )}
        </section>
        <section className="phone-setup-card">
          <div className="phone-setup-heading">
            <span className="eyebrow">ТВОИ ПРАВИЛА</span>
            <h2>Настроим вечер</h2>
          </div>
          <GameSetup
            initial={{
              name: s.room_name,
              mode: s.mode,
              count: s.count,
              capacity: s.capacity,
            }}
            modes={meta.modes}
            busy={busy}
            players={players.length}
            onSubmit={(body) => act("settings", body)}
          />
        </section>
      </>
    );
  }

  return (
    <div className={"app " + (isTV ? "tv" : "phone minimal")}>
      <header>
        <a className="brand" href={isTV ? "/tv" : "/play"}>
          <span>?</span> Я за БЕНГЕР
        </a>
        <span className={"connection " + (!online ? "offline" : "")}>
          {online
            ? isTV
              ? "ВЕЧЕР СТРАННЫХ РЕШЕНИЙ"
              : me?.name || "Контроллер"
            : "Нет связи"}
        </span>
      </header>
      {error && (
        <div className="error" role="alert">
          {error}
          {!isTV && <button onClick={() => setError("")}>×</button>}
        </div>
      )}
      {!isTV && (
        <nav className="room-navigation">
          <a href="/play">← Все комнаты</a>
          <span>
            {s?.room_name || "Комната"} <b>{roomCode}</b>
          </span>
          <a
            href={"/tv?room=" + encodeURIComponent(roomCode)}
            target="_blank"
            rel="noreferrer"
          >
            Экран ↗
          </a>
        </nav>
      )}
      {missingRoom ? (
        <section className="room-missing">
          <h1>Комната не найдена</h1>
          <p>Проверь код или собери новую компанию.</p>
          <a href={isTV ? "/tv" : "/play"}>Все комнаты →</a>
        </section>
      ) : !s || !meta ? (
        <div className="waiting">
          <h2>Подключаемся…</h2>
        </div>
      ) : !isTV && !me ? (
        <form
          className="simple-join"
          onSubmit={(e) => {
            e.preventDefault();
            act("join", { name });
          }}
        >
          <span className="eyebrow">ВХОД В КОМНАТУ {roomCode}</span>
          <h1>Как тебя звать?</h1>
          <input
            aria-label="Твоё имя"
            autoComplete="nickname"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={20}
            placeholder="Твоё имя"
            required
          />
          <button className="primary" disabled={busy}>
            Войти <ArrowRight size={19} />
          </button>
          <p className="helper">Пати-игра для своих</p>
        </form>
      ) : s.phase === "lobby" ? (
        isTV ? (
          <Lobby
            roomCode={s.room_code}
            roomName={s.room_name}
            players={players}
            capacity={capacity}
            origin={origin}
            modeTitle={
              s.mode === "mix" ? "Микс бенгеров" : meta.modes[s.mode][0]
            }
            count={s.count}
            leaderName={s.leader_name}
          />
        ) : (
          <>
            <div className="phone-title">
              <span className="eyebrow">
                ОЖИДАНИЕ НАЧАЛА · {players.length}
                {capacity !== null && "/" + capacity}
              </span>
              <h1>Ты в лобби</h1>
            </div>
            <ul className="roster">
              {players.map((p) => (
                <li key={p.id}>
                  <span>
                    {p.name}
                    {p.id === me.id && <small> ты</small>}
                  </span>
                  {s.is_leader && p.id !== me.id && (
                    <button
                      aria-label={"Убрать " + p.name}
                      className="text-button"
                      onClick={() =>
                        act("players/" + p.id, undefined, "DELETE")
                      }
                    >
                      ×
                    </button>
                  )}
                </li>
              ))}
            </ul>
            {s.is_leader ? (
              settings()
            ) : (
              <p className="helper">
                {s.leader_name} выбирает игру. Смотри на телевизор.
              </p>
            )}
            <button className="text-button leave" onClick={leave}>
              Выйти
            </button>
          </>
        )
      ) : me?.waiting && s.phase !== "final" ? (
        <div className="phone-title">
          <h1>Следующая партия — твоя</h1>
          <p className="helper">Сейчас игра уже идёт.</p>
        </div>
      ) : s.phase === "final" ? (
        <>
          <section className="final-hero">
            {isTV && <PartyBurst key={phaseKey} />}
            <Crown className="winner-crown" aria-hidden="true" />
            <span className="eyebrow">ФИНАЛ</span>
            <h1>
              {scores
                .filter((p) => p.score === scores[0]?.score)
                .map((p) => p.name)
                .join(" + ")}
              <br />
              <i>на троне!</i>
            </h1>
          </section>
          {scoreboard}
          {benger && (
            <section className="panel hit">
              <span className="eyebrow">БЕНГЕР ВЕЧЕРА</span>
              <h2>«{benger.text}»</h2>
              {benger.image && (
                <img
                  className="benger-image"
                  src={imageSource(benger.image)}
                  alt={benger.text}
                />
              )}
            </section>
          )}
          {!isTV && s.is_leader && (
            <div className="actions">
              <button
                className="primary"
                disabled={busy || players.length < minimum}
                onClick={() => act("start")}
              >
                Реванш <RotateCcw size={18} />
              </button>
              <button
                className="text-button"
                disabled={busy}
                onClick={() => act("lobby")}
              >
                Другая игра
              </button>
            </div>
          )}
        </>
      ) : (
        <>
          <div className="round-top">
            <div>
              <span className="chip">
                {s.index + 1}/{s.count}
              </span>
              <span className="chip">{mode?.[0]}</span>
            </div>
            {s.deadline && (
              <span className={"timer " + (seconds <= 10 ? "urgent" : "")}>
                {seconds}
                <small>сек</small>
              </span>
            )}
          </div>
          <section
            key={r.round_id}
            className={"prompt-panel " + (mode?.[3] || "lav")}
          >
            {isTV && (
              <span className="round-sticker" aria-hidden="true">
                <Sticker index={(s.index * 2 + 4) % 9} />
              </span>
            )}
            <h1>{r.prompt}</h1>
            <p>{r.context}</p>
            {r.callback && <blockquote>«{r.callback}»</blockquote>}
          </section>
          {shownImage && (
            <img
              className="scene-image"
              src={imageSource(shownImage)}
              alt="Картинка для подписи"
            />
          )}
          {s.phase === "briefing" ? (
            <section className="simple-wait">
              <Sparkles className="sparkle" />
              <h2>Рисуем картинку для всех</h2>
              <p>Таймер начнётся, когда она появится.</p>
            </section>
          ) : ["answer", "caption"].includes(s.phase) ? (
            isTV ? (
              <section className="tv-wait">
                <div className="wait-mascot" aria-hidden="true">
                  <Sticker index={isImage ? 2 : 4} />
                  <span>✦</span>
                  <span>✺</span>
                </div>
                <div>
                  <span className="eyebrow">
                    {isCaption
                      ? "ВТОРОЙ ХОД · ПОДПИСЫВАЕМ КАРТИНКИ"
                      : "ОТВЕЧАЕМ НА ТЕЛЕФОНАХ"}
                  </span>
                  <h2>
                    {isCaption
                      ? "Чужая картинка. Твой бенгер."
                      : "Делаем бенгер."}
                  </h2>
                  <p>
                    {s.ready} /{" "}
                    {isCaption
                      ? s.caption_total
                      : players.filter((p) => !p.waiting).length}{" "}
                    готово
                  </p>
                  <progress
                    aria-label="Готовность игроков"
                    max={
                      (isCaption
                        ? s.caption_total
                        : players.filter((p) => !p.waiting).length) || 1
                    }
                    value={s.ready}
                  />
                  {s.image_pending > 0 && (
                    <p>В генерации: {s.image_pending}. Ждём все картинки.</p>
                  )}
                </div>
              </section>
            ) : s.submitted ? (
              <section className="simple-wait">
                <Check size={36} />
                <h2>
                  {isRelay && isImage
                    ? "Картинка передана дальше"
                    : "Ответ принят"}
                </h2>
                <p>Смотри на телевизор.</p>
              </section>
            ) : pendingGeneration ? (
              <section className="simple-wait" aria-live="polite">
                <Sparkles className="sparkle" size={36} />
                <h2>
                  {s.image_retry
                    ? "Снова пробуем нарисовать"
                    : "Рисуем твой бенгер"}
                </h2>
                <p>Описание сохранено. Можно закрыть страницу и вернуться.</p>
              </section>
            ) : isCaption && !s.caption_image ? (
              <section className="simple-wait">
                <h2>Ждём подписи остальных</h2>
                <p>В этом раунде тебе не досталась картинка.</p>
              </section>
            ) : (
              <>
                {ability}
                {s.image_error && (
                  <p className="provider-error" role="alert">
                    {s.image_error}
                  </p>
                )}
                <form
                  className="simple-answer"
                  onSubmit={(e) => {
                    e.preventDefault();
                    isImage && !uploaded
                      ? generate()
                      : act("answer", {
                          image: isImage ? uploaded : null,
                          text: fieldNames
                            ? [text.trim(), second.trim()].join("\n")
                            : text,
                          power,
                          round_id: r.round_id,
                        });
                  }}
                >
                  <label>
                    {isImage
                      ? "Что нарисовать?"
                      : fieldNames?.[0] ||
                        (shownImage ? "Подпись к картинке" : "Твой бенгер")}
                    <textarea
                      value={text}
                      onChange={(e) =>
                        setText(
                          fieldNames
                            ? e.target.value.replace(/[\r\n]+/g, " ")
                            : e.target.value,
                        )
                      }
                      maxLength={fieldNames ? 119 : 240}
                      disabled={busy}
                      placeholder={
                        uploaded
                          ? "Подпись по желанию"
                          : isImage
                            ? "Например: сова в бухгалтерии"
                            : "Одна смешная фраза"
                      }
                      required={!uploaded}
                    />
                  </label>
                  {isImage && (
                    <div className="clue-upload-control">
                      <label>
                        Своя картинка
                        <input
                          type="file"
                          accept="image/png,image/jpeg,image/webp"
                          onChange={uploadClue}
                          disabled={busy}
                        />
                      </label>
                      {uploaded && (
                        <>
                          <img src={imageSource(uploaded)} alt="Твоя картинка" />
                          <button type="button" onClick={() => setUpload(null)}>
                            Убрать картинку
                          </button>
                        </>
                      )}
                    </div>
                  )}
                  {fieldNames && (
                    <label>
                      {fieldNames[1]}
                      <input
                        value={second}
                        maxLength={119}
                        onChange={(e) => setSecond(e.target.value)}
                        disabled={busy}
                        placeholder="Здесь панчлайн"
                        required
                      />
                    </label>
                  )}
                  <button
                    className="primary"
                    disabled={
                      busy ||
                      (!uploaded && !text.trim()) ||
                      (fieldNames && !second.trim()) ||
                      (isImage &&
                        !uploaded &&
                        (text.trim().length < 3 ||
                          meta.image_provider === "local"))
                    }
                  >
                    {isImage && !uploaded ? (
                      <>
                        Создать картинку <Sparkles size={20} />
                      </>
                    ) : (
                      <>
                        Отправить бенгер <ArrowRight size={20} />
                      </>
                    )}
                  </button>
                  {isImage && (
                    <p className="helper">
                      {meta.image_provider === "local"
                        ? "Можно сыграть со своей картинкой."
                        : isRelay
                          ? "Картинку подпишет другой игрок."
                          : "Описание станет подписью. Картинка отправится сама."}
                    </p>
                  )}
                </form>
              </>
            )
          ) : s.phase === "vote" ? (
            <>
              <div className="section-heading">
                <h2>{s.voted ? "Голос принят" : "Кто тут бенгер?"}</h2>
                {isTV && <span>{s.ready} голосов</span>}
              </div>
              {!isTV && s.voted ? (
                <section className="simple-wait">
                  <Check size={30} />
                  <p>Смотри на телевизор.</p>
                </section>
              ) : (
                <>
                  {!isTV && me.power === "block" && !me.spent && (
                    <p className="helper block-hint">
                      ∅ обнуляет очки выбранного ответа. Один раз за партию.
                    </p>
                  )}
                  {answers(r)}
                  {!isTV && (
                    <div className="vote-submit">
                      <button
                        className="primary"
                        disabled={!pick || busy}
                        onClick={() =>
                          act("vote", {
                            answer: pick,
                            block: block || null,
                            round_id: r.round_id,
                          })
                        }
                      >
                        Подтвердить <Check size={18} />
                      </button>
                    </div>
                  )}
                </>
              )}
            </>
          ) : isTV ? (
            <>
              <div className="section-heading reveal-heading">
                <PartyBurst key={phaseKey} />
                <h2>
                  Вот где <i>бенгер.</i>
                </h2>
                <span className="reveal-stamp">УЛИКИ ВСКРЫТЫ</span>
              </div>
              {s.image_error && (
                <p className="provider-error">{s.image_error}</p>
              )}
              {answers(r, true)}
              <div className="reveal-bottom">
                {scoreboard}
                {continueBox}
              </div>
            </>
          ) : (
            <>
              <section className="personal-result">
                <span className="eyebrow">ТВОЙ РЕЗУЛЬТАТ</span>
                <strong>+{ownPoints}</strong>
                <p>{me.score} баллов за партию</p>
              </section>
              {continueBox}
              <details className="all-results">
                <summary>Все ответы и голоса</summary>
                {answers(r, true)}
              </details>
            </>
          )}
          {!isTV && me && (
            <div className="player-status">
              <span>{me.score} б.</span>
              <span>
                {me.spent
                  ? "Способность использована"
                  : me.power_info[2] + " " + me.power_info[0]}
              </span>
            </div>
          )}
        </>
      )}
      {isTV && (
        <footer>
          <span>Я ЗА БЕНГЕР © 2026</span>
          <span>ПЛОХИЕ ИДЕИ. ХОРОШИЙ ВЕЧЕР.</span>
        </footer>
      )}
    </div>
  );
}

export { isTV, roomCode, api };
