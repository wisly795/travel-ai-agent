// 目的地的介紹文字、配色，以及對應到開放資料的縣市、爬蟲網站的城市名稱
export const DESTINATIONS = {
  沖繩: { country: "日本", tagline: "碧海、珊瑚礁與島嶼慢時光", city: null, supplier: "沖繩", art: "okinawa" },
  京都: { country: "日本", tagline: "千年古都的寺院、庭園與楓紅", city: null, supplier: "京都", art: "kyoto" },
  首爾: { country: "韓國", tagline: "市場美食、街區咖啡與夜景", city: null, supplier: "首爾", art: "seoul" },
  花蓮: { country: "台灣", tagline: "峽谷、清水斷崖與太平洋", city: "花蓮縣", supplier: "花蓮", art: "hualien" },
  台東: { country: "台灣", tagline: "縱谷稻浪、熱氣球與部落文化", city: "臺東縣", supplier: "臺東", art: "taitung" },
};

export const meta = (destination) => DESTINATIONS[destination] || { country: "", tagline: "", city: null, art: "okinawa" };

export const SOURCE_NOTE = "景點與住宿資料來源：交通部觀光署（政府資料開放授權條款第 1 版）";
