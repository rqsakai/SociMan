import { ProfileImagePicker, type ProfileImagePickerProps } from "./ProfileImagePicker";

const TIPOS = ["fundo", "cenario"] as const;

// Imagem de fundo do gancho e do card final (FR-005b da 004; FR-006 da 007): escolhe entre os
// fundos e os cenários da biblioteca do perfil (Q2 = A). Enviar cria um "Fundo" na biblioteca.
export function FundoImagePicker({ perfilId, ...props }: ProfileImagePickerProps & { perfilId: string }) {
  return (
    <ProfileImagePicker
      {...props}
      perfilId={perfilId}
      tipos={TIPOS}
      uploadTipo="fundo"
      label="Imagem de fundo"
      uploadLabel="Enviar imagem de fundo"
      hint="Fundos e cenários da biblioteca. PNG, JPG ou WebP, até 20 MB, mínimo 540×540 px. A imagem é recortada para preencher a área."
    />
  );
}
