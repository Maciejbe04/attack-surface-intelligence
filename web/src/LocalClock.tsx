import { useEffect, useState } from "react";

function timezoneOffsetLabel(now: Date): string {
  for (const option of ["shortOffset", "short"] as const) {
    try {
      const value = new Intl.DateTimeFormat(undefined, {
        timeZoneName: option,
      })
        .formatToParts(now)
        .find((part) => part.type === "timeZoneName")?.value;
      if (value) return value;
    } catch {
      /* older engines may not support shortOffset */
    }
  }
  const minutes = -now.getTimezoneOffset();
  const sign = minutes >= 0 ? "+" : "-";
  const abs = Math.abs(minutes);
  const hh = String(Math.floor(abs / 60)).padStart(2, "0");
  const mm = String(abs % 60).padStart(2, "0");
  return `GMT${sign}${hh}:${mm}`;
}

function readClock() {
  const now = new Date();
  const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  const time = new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(now);
  return {
    time,
    timeZone,
    offset: timezoneOffsetLabel(now),
    iso: now.toISOString(),
  };
}

export function LocalClock({ className = "" }: { className?: string }) {
  const [clock, setClock] = useState(readClock);

  useEffect(() => {
    const tick = () => setClock(readClock());
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, []);

  const label = [clock.timeZone, clock.offset].filter(Boolean).join(" · ");

  return (
    <time
      className={`local-clock mono ${className}`.trim()}
      dateTime={clock.iso}
      title={label}
    >
      <span className="local-clock__time">{clock.time}</span>
      <span className="local-clock__zone">{label}</span>
    </time>
  );
}
