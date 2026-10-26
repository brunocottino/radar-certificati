// Orologio del robot: Cloudflare Cron Triggers (gratuiti e puntuali) avviano la run di GitHub Actions.
// GitHub ritarda di ore o salta le run programmate (26/10: nessuna delle 5 del mattino è partita).
// Cron (UTC) da impostare nel Worker: "35,40 7,8 * * 1-5" e "15,20 14,15 * * 1-5".
// Parte solo nelle finestre 09:35-09:49 e 16:15-16:29 di Roma (così vale con ora legale e solare); due scatti
// a 5 minuti per sicurezza: il workflow (input auto) salta se la fascia è già pubblicata o la borsa è chiusa.
// Segreto richiesto: GH_TOKEN = token GitHub "fine-grained" con accesso al solo repository e permesso Actions: write.
const REPO = "brunocottino/radar-certificati";

function romeHM(d = new Date()) {
  const p = Object.fromEntries(new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/Rome", hour: "2-digit", minute: "2-digit", weekday: "short", hourCycle: "h23",
  }).formatToParts(d).map(x => [x.type, x.value]));
  return { hm: +(p.hour + p.minute), wd: p.weekday };
}

async function dispatch(env) {
  const r = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/scrape.yml/dispatches`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${env.GH_TOKEN}`, accept: "application/vnd.github+json",
      "x-github-api-version": "2022-11-28", "user-agent": "radar-cron",
    },
    body: JSON.stringify({ ref: "main", inputs: { auto: "true" } }),
  });
  return r.status;  // 204 = avviata
}

export default {
  async scheduled(event, env, ctx) {
    const { hm, wd } = romeHM(new Date(event.scheduledTime));
    if (["Sat", "Sun"].includes(wd)) return;
    if (!((hm >= 935 && hm < 950) || (hm >= 1615 && hm < 1630))) return;  // occorrenza dell'altro fuso
    const st = await dispatch(env);
    console.log(`Roma ${hm}: avvio robot → HTTP ${st}`);
  },
  // GET /?prova=1 non serve: per provarlo usare "Trigger scheduled event" nel pannello o il log del Worker
  async fetch() { return new Response("radar-cron", { status: 200 }); },
};
