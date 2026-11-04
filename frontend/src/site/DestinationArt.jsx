// 目的地插畫（自己畫的 SVG，沒有版權問題）：海外目的地沒有可授權的照片，用插畫代替
import React from "react";

const SCENES = {
  okinawa: {
    sky: ["#7dd3fc", "#e0f2fe"],
    body: (
      <>
        <circle cx="320" cy="70" r="28" fill="#fde68a" />
        <path d="M0 160 Q100 140 200 158 T400 150 V240 H0Z" fill="#38bdf8" />
        <path d="M0 185 Q120 165 240 182 T400 178 V240 H0Z" fill="#0ea5e9" />
        <path d="M0 212 Q100 198 220 210 T400 205 V240 H0Z" fill="#fef3c7" />
        <path d="M86 210 C90 170 96 140 104 118" stroke="#78350f" strokeWidth="6" fill="none" strokeLinecap="round" />
        <path d="M104 118 C84 104 64 106 50 118 M104 118 C120 98 142 96 156 106 M104 118 C100 96 108 80 122 72 M104 118 C90 100 76 88 60 88"
              stroke="#15803d" strokeWidth="7" fill="none" strokeLinecap="round" />
      </>
    ),
  },
  kyoto: {
    sky: ["#fb923c", "#fde68a"],
    body: (
      <>
        <circle cx="300" cy="96" r="34" fill="#fff7ed" opacity="0.8" />
        <path d="M0 190 Q80 160 160 176 T320 168 T400 172 V240 H0Z" fill="#9a3412" opacity="0.55" />
        <g fill="#431407">
          <rect x="92" y="96" width="44" height="124" />
          <path d="M70 100 H158 L146 88 H82Z" /><path d="M74 134 H154 L144 122 H84Z" /><path d="M78 168 H150 L140 156 H88Z" />
          <rect x="112" y="64" width="4" height="26" />
        </g>
        <g fill="#7f1d1d">
          <rect x="230" y="150" width="8" height="70" /><rect x="290" y="150" width="8" height="70" />
          <path d="M214 146 H314 L306 136 H222Z" /><rect x="226" y="160" width="76" height="6" />
        </g>
        <path d="M0 220 H400 V240 H0Z" fill="#431407" />
      </>
    ),
  },
  seoul: {
    sky: ["#312e81", "#a78bfa"],
    body: (
      <>
        <g fill="#fef9c3">
          <circle cx="60" cy="40" r="1.6" /><circle cx="140" cy="28" r="1.4" /><circle cx="250" cy="46" r="1.6" /><circle cx="350" cy="30" r="1.4" />
        </g>
        <path d="M0 190 Q100 150 200 170 T400 160 V240 H0Z" fill="#4c1d95" opacity="0.7" />
        <g fill="#1e1b4b">
          <rect x="196" y="70" width="8" height="110" /><ellipse cx="200" cy="104" rx="18" ry="8" />
          <rect x="199" y="44" width="2" height="26" />
          <rect x="20" y="170" width="40" height="70" /><rect x="64" y="150" width="30" height="90" /><rect x="100" y="180" width="50" height="60" />
          <rect x="250" y="160" width="36" height="80" /><rect x="292" y="140" width="28" height="100" /><rect x="326" y="175" width="60" height="65" />
        </g>
        <g fill="#fde68a" opacity="0.8">
          <rect x="70" y="160" width="4" height="4" /><rect x="80" y="176" width="4" height="4" /><rect x="298" y="150" width="4" height="4" />
          <rect x="306" y="170" width="4" height="4" /><rect x="260" y="174" width="4" height="4" />
        </g>
      </>
    ),
  },
  hualien: {
    sky: ["#93c5fd", "#ecfeff"],
    body: (
      <>
        <path d="M0 150 L70 70 L120 120 L180 50 L250 130 L300 90 L400 160 V240 H0Z" fill="#166534" opacity="0.75" />
        <path d="M0 170 L90 110 L150 150 L220 100 L300 160 L400 140 V240 H0Z" fill="#15803d" />
        <path d="M0 200 Q100 186 200 198 T400 194 V240 H0Z" fill="#0284c7" />
        <path d="M0 220 Q100 208 200 218 T400 214 V240 H0Z" fill="#0369a1" />
      </>
    ),
  },
  taitung: {
    sky: ["#fcd34d", "#fef9c3"],
    body: (
      <>
        <path d="M0 140 L90 90 L170 130 L260 80 L400 130 V240 H0Z" fill="#65a30d" opacity="0.6" />
        <g>
          <ellipse cx="300" cy="70" rx="22" ry="26" fill="#ef4444" />
          <path d="M282 80 Q300 100 318 80" fill="#f97316" />
          <rect x="294" y="98" width="12" height="10" fill="#92400e" />
          <path d="M290 92 L296 98 M310 92 L304 98" stroke="#92400e" strokeWidth="1.5" />
        </g>
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <path key={i} d={`M0 ${160 + i * 14} Q200 ${150 + i * 14} 400 ${160 + i * 14} V${174 + i * 14} Q200 ${164 + i * 14} 0 ${174 + i * 14}Z`}
                fill={i % 2 ? "#84cc16" : "#a3e635"} />
        ))}
      </>
    ),
  },
};

export default function DestinationArt({ art, label, className = "" }) {
  const scene = SCENES[art] || SCENES.okinawa;
  const id = `sky-${art}`;
  return (
    <svg className={`dest-art ${className}`} viewBox="0 0 400 240" preserveAspectRatio="xMidYMid slice" role="img" aria-label={label}>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={scene.sky[0]} /><stop offset="1" stopColor={scene.sky[1]} />
        </linearGradient>
      </defs>
      <rect width="400" height="240" fill={`url(#${id})`} />
      {scene.body}
    </svg>
  );
}
