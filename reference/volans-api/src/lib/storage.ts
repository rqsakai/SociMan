// Interface de Object Storage do starter (análogo do storage da Azion / S3).
// O boilerplate de auth não faz upload — a interface existe para as recipes
// herdeiras já nascerem com o contrato certo. Implementação S3/MinIO em
// adapters/s3Storage.ts, selecionada por STORAGE_DRIVER.
export interface ObjectStorage {
  put(key: string, body: Uint8Array | string, contentType?: string): Promise<void>;
  get(key: string): Promise<Uint8Array | null>;
  delete(key: string): Promise<void>;
}
