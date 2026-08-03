// ponytail: hand-rolled minimal PDF (no library) — content must stay ASCII so
// string .length matches byte offsets for the xref table below.
function pdfEscape(text: string) {
  return text.replace(/\\/g, "\\\\").replace(/\(/g, "\\(").replace(/\)/g, "\\)");
}

export function formatPdfAmount(amount: number) {
  return `Rs. ${Math.round(amount).toLocaleString("en-IN")}`;
}

export function generateInvoicePdf(lines: string[]): Blob {
  const objects: string[] = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R /F2 6 0 R >> >> /MediaBox [0 0 612 792] /Contents 5 0 R >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
  ];

  const streamLines = ["BT", "/F2 18 Tf", `50 740 Td (${pdfEscape("Fashion Trendz")}) Tj`, "/F1 11 Tf"];
  lines.forEach((line, i) => {
    const dy = i === 0 ? -36 : -18;
    streamLines.push(`0 ${dy} Td (${pdfEscape(line)}) Tj`);
  });
  streamLines.push("ET");
  const stream = streamLines.join("\n");

  objects.push(`<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`);
  objects.push("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>");

  let pdf = "%PDF-1.4\n";
  const offsets: number[] = [0];
  objects.forEach((obj, index) => {
    offsets.push(pdf.length);
    pdf += `${index + 1} 0 obj\n${obj}\nendobj\n`;
  });

  const xrefStart = pdf.length;
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (let i = 1; i <= objects.length; i++) {
    pdf += `${offsets[i].toString().padStart(10, "0")} 00000 n \n`;
  }
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefStart}\n%%EOF`;

  return new Blob([pdf], { type: "application/pdf" });
}

export function downloadInvoicePdf(filename: string, lines: string[]) {
  const blob = generateInvoicePdf(lines);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
