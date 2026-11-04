import React from "react";
import useStaffData from "./useStaffData.js";

export default function Usage({ staffApi, version, onError }) {
  const [usage] = useStaffData(staffApi, "/api/admin/usage", version, onError);
  return (
    <div id="usage" className="stats">
      {usage && [
        ["今日 AI 對話", `${usage.turns} / ${usage.turn_limit} 次`],
        ["今日 AI 花費", `US$ ${Number(usage.cost_usd).toFixed(4)} / ${usage.cost_limit_usd}`],
      ].map(([label, value]) => (
        <div key={label} className="stat"><small>{label}</small><strong>{value}</strong></div>
      ))}
    </div>
  );
}
