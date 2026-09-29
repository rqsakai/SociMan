import { handleConfig } from "@/handlers/config";
import { getDefaultDeps } from "@/handlers/deps";

export const GET = (req: Request) => handleConfig(req, getDefaultDeps());
