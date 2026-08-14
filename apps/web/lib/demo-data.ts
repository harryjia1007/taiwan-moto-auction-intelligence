import { matchesDisplacementBand, type DisplacementBand, type MotorcycleClass } from "@tm-ai/shared";

export interface DemoMotorcycle {
  id: string;
  title: string;
  sourceLabel: string;
  county: string;
  vehicleClass: MotorcycleClass;
  displacementCc: number | null;
  auctionAt: string;
  price: number | null;
  eligibility: string;
  registration: string;
  condition: string;
  imageTone: "green" | "copper" | "blue";
}

const day = 86_400_000;

export function syntheticDemoMotorcycles(now = new Date()): DemoMotorcycle[] {
  const at = (offset: number) => new Date(now.getTime() + offset * day).toISOString();
  return [
    { id: "demo-ordinary-125", title: "都會通勤機車 A", sourceLabel: "政府標售來源示意", county: "臺北市", vehicleClass: "ORDINARY_HEAVY", displacementCc: 125, auctionAt: at(5), price: 18_000, eligibility: "一般民眾可投標", registration: "需重新確認領牌條件", condition: "有鑰匙；發動狀態未確認", imageTone: "green" },
    { id: "demo-large-550", title: "大型重型機車 B", sourceLabel: "司法拍賣來源示意", county: "臺中市", vehicleClass: "LARGE_HEAVY", displacementCc: 550, auctionAt: at(12), price: 86_000, eligibility: "投標資格未確認", registration: "牌照狀態未確認", condition: "可否測試未確認", imageTone: "copper" },
    { id: "demo-electric", title: "電動機車 C", sourceLabel: "公有財產標售示意", county: "高雄市", vehicleClass: "ELECTRIC_MOTORCYCLE", displacementCc: null, auctionAt: at(26), price: 12_500, eligibility: "一般民眾可投標", registration: "可正常過戶", condition: "電池健康度未確認", imageTone: "blue" },
    { id: "demo-ended", title: "普通輕型機車 D", sourceLabel: "歷史案件示意", county: "臺南市", vehicleClass: "ORDINARY_LIGHT", displacementCc: 50, auctionAt: at(-14), price: null, eligibility: "一般民眾可投標", registration: "結果待官方確認", condition: "已截止不代表已成交", imageTone: "green" },
  ];
}

export function filterDemoMotorcycles(items: DemoMotorcycle[], filters: { view: "active" | "ended"; within?: number; vehicleClass?: MotorcycleClass; cc?: DisplacementBand[] }, now = new Date()) {
  return items.filter((item) => {
    const delta = new Date(item.auctionAt).getTime() - now.getTime();
    if (filters.view === "active" && delta < 0) return false;
    if (filters.view === "ended" && delta >= 0) return false;
    if (filters.within !== undefined && (delta < 0 || delta > filters.within * day)) return false;
    if (filters.vehicleClass && item.vehicleClass !== filters.vehicleClass) return false;
    if (filters.cc?.length && !filters.cc.some((band) => matchesDisplacementBand(item.displacementCc, band))) return false;
    return true;
  });
}
