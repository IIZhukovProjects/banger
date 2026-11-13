import React, { useMemo } from "react";
import qrcode from "qrcode-generator";
import { ArrowUpRight } from "lucide-react";

function JoinCode({ url }) {
  const { size, path } = useMemo(() => {
    const code = qrcode(0, "M");
    code.addData(url);
    code.make();
    const modules = code.getModuleCount();
    const pieces = [];
    for (let y = 0; y < modules; y++) {
      for (let x = 0; x < modules; x++) {
        if (code.isDark(y, x))
          pieces.push("M" + (x + 4) + " " + (y + 4) + "h1v1h-1z");
      }
    }
    return { size: modules + 8, path: pieces.join("") };
  }, [url]);
  return (
    <svg
      className="join-qr"
      viewBox={"0 0 " + size + " " + size}
      role="img"
      aria-label="QR-код для входа в игру"
      shapeRendering="crispEdges"
    >
      <rect width={size} height={size} fill="#fff9ea" />
      <path d={path} fill="#29173d" />
    </svg>
  );
}

export default function Lobby({
  roomCode,
  roomName,
  players,
  capacity,
  origin,
  modeTitle,
  count,
  leaderName,
}) {
  const url = origin + "/play?room=" + encodeURIComponent(roomCode);
  const rounds =
    count % 10 === 1 && count % 100 !== 11
      ? "раунд"
      : count % 10 >= 2 &&
          count % 10 <= 4 &&
          (count % 100 < 12 || count % 100 > 14)
        ? "раунда"
        : "раундов";
  const address = url.replace(/^https?:\/\//, "");
  return (
    <div className="lobby-screen">
      <div className="room-identity">
        <div>
          <span className="eyebrow">ВАША КОМНАТА</span>
          <h2>{roomName}</h2>
        </div>
        <a href="/tv">← Все комнаты</a>
      </div>
      <div className="lobby-top">
        <section className="hero" aria-label="Я за БЕНГЕР">
          <div className="hero-copy">
            <span className="eyebrow dark">СВОИ ЛЮДИ. СТРАННЫЕ ОТВЕТЫ.</span>
            <h1>
              <span className="hero-first">Я за</span>
              <span>БЕНГЕР</span>
            </h1>
            <p>
              Твой ответ. Их голоса.
              <br />А потом выясним, кто за это.
            </p>
          </div>
          <img src="/assets/mouth.jpg" alt="Пластилиновый персонаж с билетом" />
          <span className="hero-edition" aria-hidden="true">
            ✦ &nbsp; ВЕЧЕР ОБЕЩАЕТ БЫТЬ
          </span>
        </section>
        <aside className="join-box panel" aria-labelledby="join-title">
          <div className="ticket-top">
            <span className="eyebrow">ТВОЙ БИЛЕТ В БАНДУ</span>
            <span className="ticket-arrow" aria-hidden="true">
              <ArrowUpRight size={21} />
            </span>
          </div>
          <h2 id="join-title">
            Залетай.
            <br />
            <span>Тут все свои.</span>
          </h2>
          <div className="qr-stage">
            <div className="qr-paper">
              <JoinCode url={url} />
            </div>
            <span className="ticket-seal" aria-hidden="true">
              ✦
            </span>
            <span className="qr-caption" aria-hidden="true">
              НАВОДИ КАМЕРУ ↗
            </span>
          </div>
          <div className="ticket-stub">
            <div className="room-ticket-code">
              <span>КОД КОМНАТЫ</span>
              <strong>{roomCode}</strong>
            </div>
            <p>Или открой на телефоне</p>
            <a
              className="join-address"
              href={url}
              target="_blank"
              rel="noreferrer"
            >
              {address}
            </a>
            <small>Один телефон — один игрок</small>
          </div>
        </aside>
      </div>
      <div className="lobby-summary">
        <section className="players-bar" aria-labelledby="players-title">
          <div className="band-count">
            <span className="eyebrow" id="players-title">
              БАНДА В СБОРЕ?
            </span>
            <h3>
              {players.length}
              <span>{capacity === null ? " / ∞" : " / " + capacity}</span>
            </h3>
          </div>
          <div className="player-list">
            {players.length ? (
              players.map((player, index) => (
                <span className="player-pill" key={player.id}>
                  <span className={"avatar a" + (index % 4)}>
                    {player.name[0]}
                  </span>
                  {player.name}
                </span>
              ))
            ) : (
              <div className="empty-lobby">
                <span className="empty-avatars" aria-hidden="true">
                  <i>?</i>
                  <i>?</i>
                  <i>?</i>
                </span>
                <p>
                  Первый смелый
                  <br />
                  <strong>выбирает игру.</strong>
                </p>
              </div>
            )}
          </div>
        </section>
        <section className="tv-playlist">
          <span className="playlist-disc" aria-hidden="true" />
          <div>
            <span className="eyebrow">НА ЭТОТ ВЕЧЕР</span>
            <h2>{modeTitle}</h2>
            <p>
              {count} {rounds} ·{" "}
              {leaderName
                ? leaderName + " запускает игру с телефона"
                : "Режим можно выбрать после входа"}
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}
