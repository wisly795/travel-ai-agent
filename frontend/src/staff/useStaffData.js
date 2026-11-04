import { useEffect, useState } from "react";

// 載入一支後台 API；version 改變（做完動作）時重新載入。失敗時顯示錯誤訊息。
export default function useStaffData(staffApi, path, version, onError, initial = null) {
  const [data, setData] = useState(initial);
  useEffect(() => {
    let alive = true;
    staffApi(path).then((value) => { if (alive) setData(value); }).catch((error) => onError(error.message));
    return () => { alive = false; };
  }, [staffApi, path, version]);
  return [data, setData];
}
