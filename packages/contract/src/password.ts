import { z } from "zod";

export const PASSWORD_MIN_LENGTH_DEFAULT = 8;
export const PASSWORD_MAX_LENGTH = 128;

// Senhas óbvias bloqueadas mesmo quando passam no tamanho mínimo.
// Comparação é feita em lowercase.
export const commonPasswords = new Set([
  "12345678",
  "123456789",
  "1234567890",
  "password",
  "password1",
  "password123",
  "senha1234",
  "12341234",
  "qwertyui",
  "qwerty123",
  "11111111",
  "00000000",
  "abcd1234",
  "iloveyou",
  "sunshine",
  "football",
  "baseball",
  "princess",
  "dragon123",
  "letmein1",
  "welcome1",
  "admin123",
  "mudar123",
  "brasil123",
]);

export function passwordSchema(minLength: number = PASSWORD_MIN_LENGTH_DEFAULT) {
  return z
    .string()
    .min(minLength, `A senha precisa ter pelo menos ${minLength} caracteres`)
    .max(PASSWORD_MAX_LENGTH, `A senha pode ter no máximo ${PASSWORD_MAX_LENGTH} caracteres`)
    .refine((value) => !commonPasswords.has(value.toLowerCase()), {
      message: "Essa senha é muito comum — escolha outra",
    });
}
