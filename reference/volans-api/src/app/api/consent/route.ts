import { handleConsent } from "@/handlers/consent";
import { getDefaultDeps } from "@/handlers/deps";

export const POST = (req: Request) => handleConsent(req, getDefaultDeps());
