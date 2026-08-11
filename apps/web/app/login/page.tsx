import { Bike } from "lucide-react";
import { requestMagicLink } from "./actions";

export default async function LoginPage({ searchParams }: { searchParams: Promise<Record<string,string|undefined>> }) {
  const params = await searchParams;
  return <main className="login-shell"><section className="login-card"><span className="brand-mark"><Bike size={19}/></span><div className="eyebrow" style={{marginTop:18}}>Private intelligence workspace</div><h1>臺灣機車拍賣情報</h1><p className="muted">這是私人唯讀儀表板。輸入設定的擁有者信箱，我們會寄送一次性登入連結。</p>
    {params.sent && <p className="notice">登入連結已寄出。若使用本機 Supabase，請到 Mailpit 開啟郵件。</p>}
    {params.error && <p className="notice error">{params.error==="config"?"尚未設定 Supabase 環境變數。":params.error==="owner"?"這個信箱不在擁有者白名單中。":"登入連結目前無法寄出。"}</p>}
    <form action={requestMagicLink}><label htmlFor="email">擁有者信箱</label><input className="input" id="email" name="email" type="email" required autoComplete="email" placeholder="owner@example.com"/><button className="button" type="submit">寄送登入連結</button></form>
    <p className="muted" style={{fontSize:13}}>系統不會使用此登入流程連線或登入任何拍賣網站。</p>
  </section></main>;
}
