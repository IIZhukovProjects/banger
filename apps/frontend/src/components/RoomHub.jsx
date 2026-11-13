import React, { useEffect, useState } from "react";
import { ArrowRight, ArrowUpRight, Plus, Ticket, Users } from "lucide-react";
import GameSetup from "./GameSetup";

const PHASES = {
  lobby: "Собираются",
  briefing: "Играют",
  answer: "Играют",
  caption: "Играют",
  vote: "Голосуют",
  reveal: "Результаты",
  final: "Финал",
};

export function roomPath(code, tv = false) {
  return (tv ? "/tv" : "/play") + "?room=" + encodeURIComponent(code);
}

export default function RoomHub({ request, isTV }) {
  const [meta, setMeta] = useState(null);
  const [rooms, setRooms] = useState([]);
  const [tab, setTab] = useState(isTV ? "create" : "join");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true,
      loading = false;
    request("meta")
      .then((data) => {
        if (alive) setMeta(data);
      })
      .catch(() => {
        if (alive)
          setError("Не удалось загрузить каталог игр. Обнови страницу.");
      });
    async function refresh() {
      if (loading) return;
      loading = true;
      try {
        const data = await request("rooms");
        if (alive) setRooms(data.rooms);
      } catch {
        if (alive) setError("Комнаты пока недоступны. Проверяем соединение…");
      } finally {
        loading = false;
      }
    }
    refresh();
    const interval = setInterval(refresh, 4000);
    return () => {
      alive = false;
      clearInterval(interval);
    };
  }, []);
  async function create(settings) {
    setBusy(true);
    setError("");
    try {
      const room = await request("rooms", settings);
      location.assign(roomPath(room.code, isTV));
      return true;
    } catch (reason) {
      setError(reason.message);
    } finally {
      setBusy(false);
    }
  }
  async function join(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const room = await request(
        "rooms/" + encodeURIComponent(code.trim().toUpperCase()),
      );
      location.assign(roomPath(room.code, isTV));
    } catch (reason) {
      setError(reason.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="room-hub">
      <header className="hub-header">
        <a className="brand" href={isTV ? "/tv" : "/play"}>
          <span>?</span>Я за БЕНГЕР
        </a>
        <span className="hub-tag">КАЖДОЙ БАНДЕ — СВОЯ КОМНАТА</span>
      </header>
      <main className="hub-main">
        <section className="hub-intro">
          <div>
            <span className="eyebrow">ТВОЙ ВЕЧЕР НАЧИНАЕТСЯ ЗДЕСЬ</span>
            <h1>
              Собери
              <br />
              <span>своих.</span>
            </h1>
            <p>
              Создай комнату, раздай код
              <br />и выясни, кто сегодня смешнее.
            </p>
          </div>
          <img src="/assets/mouth.jpg" alt="Пластилиновый персонаж с билетом" />
          <span className="hub-intro-stamp" aria-hidden="true">
            ВХОД ПО ПРИКОЛУ ✦
          </span>
        </section>
        <div className="hub-workspace">
          <section className="hub-form-card">
            <div
              className="hub-tabs"
              role="group"
              aria-label="Действие с комнатой"
            >
              <button
                type="button"
                aria-pressed={tab === "create"}
                onClick={() => {
                  setTab("create");
                  setError("");
                }}
              >
                <Plus size={18} />
                Создать
              </button>
              <button
                type="button"
                aria-pressed={tab === "join"}
                onClick={() => {
                  setTab("join");
                  setError("");
                }}
              >
                <Ticket size={18} />У меня есть код
              </button>
            </div>
            {error && (
              <div className="hub-error" role="alert">
                {error}
              </div>
            )}
            {tab === "create" ? (
              <>
                <div className="hub-form-heading">
                  <span className="eyebrow">СВОИ ПРАВИЛА ВЕЧЕРА</span>
                  <h2>Какой план?</h2>
                </div>
                {meta ? (
                  <GameSetup
                    modes={meta.modes}
                    busy={busy}
                    onSubmit={create}
                    creating
                  />
                ) : (
                  <p className="hub-loading">Готовим игры…</p>
                )}
              </>
            ) : (
              <form className="join-room-form" onSubmit={join}>
                <span className="eyebrow">ТВОЙ БИЛЕТ В БАНДУ</span>
                <h2>
                  Залетай
                  <br />
                  по коду.
                </h2>
                <p>
                  Шесть символов с общего экрана.
                  <br />А дальше — твоё имя и твои шутки.
                </p>
                <label>
                  Код комнаты
                  <input
                    value={code}
                    onChange={(event) =>
                      setCode(
                        event.target.value
                          .replace(/[^a-zA-Z0-9]/g, "")
                          .toUpperCase(),
                      )
                    }
                    placeholder="ABCDEF"
                    autoComplete="off"
                    autoCapitalize="characters"
                    spellCheck={false}
                    minLength={6}
                    maxLength={6}
                    required
                    disabled={busy}
                  />
                </label>
                <button
                  type="submit"
                  className="primary"
                  disabled={busy || code.length !== 6}
                >
                  Войти в комнату
                  <ArrowRight size={20} />
                </button>
              </form>
            )}
          </section>
          <aside className="hub-directory" aria-labelledby="rooms-title">
            <div className="hub-directory-heading">
              <span className="eyebrow">КТО УЖЕ СОБРАЛСЯ</span>
              <h2 id="rooms-title">
                Комнаты<span>{rooms.length}</span>
              </h2>
            </div>
            <div className="room-list">
              {rooms.map((room) => (
                <article className="room-card" key={room.code}>
                  <div className="room-card-top">
                    <span
                      className={
                        "room-phase " + (room.phase === "lobby" ? "open" : "")
                      }
                    >
                      {PHASES[room.phase] || "Играют"}
                    </span>
                    <span className="room-short-code">{room.code}</span>
                  </div>
                  <h3>{room.name}</h3>
                  <p>
                    <Users size={14} />
                    {room.players}
                    {room.capacity === null
                      ? " / ∞"
                      : " / " + room.capacity}{" "}
                    игроков<span>·</span>
                    {room.count} раунд.
                  </p>
                  <div className="room-card-actions">
                    <a className="room-enter" href={roomPath(room.code, isTV)}>
                      {isTV ? "Открыть экран" : "Войти"}
                      <ArrowUpRight size={17} />
                    </a>
                    {!isTV && (
                      <a
                        className="room-tv"
                        href={roomPath(room.code, true)}
                        target="_blank"
                        rel="noreferrer"
                      >
                        На телевизор ↗
                      </a>
                    )}
                  </div>
                </article>
              ))}
              {!rooms.length && (
                <p className="room-list-empty">
                  Пока тихо.
                  <br />
                  Самое время собрать первую банду.
                </p>
              )}
            </div>
            <p className="hub-directory-note">
              У каждой комнаты свои участники, задания и счёт.
            </p>
          </aside>
        </div>
      </main>
      <footer>
        <span>Я ЗА БЕНГЕР © 2026</span>
        <span>ПЛОХИЕ ИДЕИ. ХОРОШИЙ ВЕЧЕР.</span>
      </footer>
    </div>
  );
}
