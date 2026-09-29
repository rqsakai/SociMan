import { ProfileImagePicker, type ProfileImagePickerProps } from "./ProfileImagePicker";

const TIPOS = ["marca_dagua", "sticker"] as const;

// Imagem própria da marca d'água (T020 da 004; FR-006 da 007): escolhe entre as marcas d'água e os
// stickers da biblioteca (os dois exigem transparência, Q2 = A). Enviar cria uma "Marca d'água"
// na biblioteca (o servidor confere o alfa).
export function WatermarkImagePicker({ perfilId, ...props }: ProfileImagePickerProps & { perfilId: string }) {
  return (
    <ProfileImagePicker
      {...props}
      perfilId={perfilId}
      tipos={TIPOS}
      uploadTipo="marca_dagua"
      label="Imagem da marca d'água"
      uploadLabel="Enviar imagem"
      hint="Marcas d'água e stickers da biblioteca. PNG ou WebP com fundo transparente, até 20 MB, mínimo 64×64 px."
      transparent
    />
  );
}
