import { handle } from "@/lib/py";
export const dynamic = "force-dynamic";
export const POST = (req: Request) => handle("carbon", "runway", req);
