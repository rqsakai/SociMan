import { handleRegister } from "@/handlers/auth";
import { getDefaultDeps } from "@/handlers/deps";

export const POST = (req: Request) => handleRegister(req, getDefaultDeps());
