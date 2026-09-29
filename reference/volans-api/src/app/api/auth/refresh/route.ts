import { handleRefresh } from "@/handlers/auth";
import { getDefaultDeps } from "@/handlers/deps";

export const POST = (req: Request) => handleRefresh(req, getDefaultDeps());
