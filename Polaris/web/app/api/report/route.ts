import { handle } from "@/lib/py";
export const dynamic = "force-dynamic";
export const GET = () => handle("carbon", "report");
