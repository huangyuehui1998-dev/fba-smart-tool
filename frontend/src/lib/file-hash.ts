/** 计算文件 SHA-256（十六进制），用于发票模板服务端缓存键。 */
export async function sha256HexFromArrayBuffer(data: ArrayBuffer): Promise<string> {
  const hash = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(hash)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function sha256HexFromFile(file: File): Promise<string> {
  return sha256HexFromArrayBuffer(await file.arrayBuffer());
}

export async function sha256HexFromBase64(base64: string): Promise<string> {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return sha256HexFromArrayBuffer(bytes.buffer);
}
