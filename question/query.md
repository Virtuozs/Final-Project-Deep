# Example Query Set (draft)

Gold labels were checked against the corpus. Verify each one against the full pasal text before freezing the test set. Some pasal have several ayat, and a question may need more than one pasal.

**Format:** `ID | Type | Question | Gold pasal`
**Types:** EXP = explanation, SIT = situation, CROSS = cross-law, OOS = out of scope (no answer in the corpus)

## How to build the full set

- Target [100-150] questions. Aim for roughly 40% EXP, 30% SIT, 15% CROSS, 15% OOS.
- Write 2-3 paraphrases of the same question (formal and everyday wording) and keep them in the same split group.
- Write the test split by hand. Freeze it before any training or tuning.
- Record gold pasal as a list, since some questions have more than one correct pasal.

## A. UU 14/2008 and PP 61/2010 (Keterbukaan Informasi Publik)

| ID | Type | Question | Gold pasal |
|---|---|---|---|
| Q001 | EXP | Apa yang dimaksud dengan Informasi Publik? | UU 14/2008 P1; PP 61/2010 P1 |
| Q002 | EXP | Apa saja hak setiap orang terkait informasi publik? | UU 14/2008 P4 |
| Q003 | EXP | Informasi apa saja yang dikecualikan dari akses publik? | UU 14/2008 P17 |
| Q004 | EXP | Informasi apa yang tidak boleh dikategorikan sebagai informasi yang dikecualikan? | UU 14/2008 P18 |
| Q005 | EXP | Apa itu uji konsekuensi dan siapa yang melakukannya? | UU 14/2008 P19; PP 61/2010 P3 |
| Q006 | EXP | Apakah informasi yang dikecualikan akan tertutup selamanya? | UU 14/2008 P20; PP 61/2010 P11 |
| Q007 | EXP | Apa tugas dan tanggung jawab PPID? | UU 14/2008 P13; PP 61/2010 P14 |
| Q008 | EXP | Informasi apa yang wajib diumumkan Badan Publik secara berkala? | UU 14/2008 P9 |
| Q009 | EXP | Apa kewajiban Badan Publik kalau ada informasi yang mengancam hajat hidup orang banyak? | UU 14/2008 P10 |
| Q010 | EXP | Informasi apa yang wajib disediakan oleh partai politik? | UU 14/2008 P15 |
| Q011 | SIT | Permintaan informasi saya ke dinas tidak dijawab lebih dari 10 hari kerja. Apa yang bisa saya lakukan? | UU 14/2008 P22, P35 |
| Q012 | SIT | Kantor desa menolak memberikan dokumen anggaran desa kepada saya. Pasal apa yang relevan? | UU 14/2008 P4, P9, P35 |
| Q013 | SIT | Saya sudah mengajukan keberatan tapi atasan PPID tidak menanggapi. Ke mana saya bisa mengadu? | UU 14/2008 P36, P37 |
| Q014 | SIT | Berapa lama batas waktu saya mengajukan keberatan setelah permintaan ditolak? | UU 14/2008 P36 |
| Q015 | SIT | Instansi menghilangkan dokumen publik yang saya minta. Apa sanksinya? | UU 14/2008 P53 |
| Q016 | SIT | Badan Publik sengaja tidak memberikan informasi berkala yang wajib dibuka. Apa ancaman pidananya? | UU 14/2008 P52 |
| Q017 | SIT | Saya tidak puas dengan putusan Komisi Informasi. Apakah bisa menggugat ke pengadilan? | UU 14/2008 P47, P48 |
| Q018 | SIT | Siapa yang menanggung ganti rugi kalau Badan Publik kalah di pengadilan? | PP 61/2010 P16, P17; UU 14/2008 P58 |
| Q019 | EXP | Berapa lama jangka waktu pengecualian untuk informasi yang menghambat penegakan hukum? | PP 61/2010 P5 |
| Q020 | EXP | Apa bedanya mediasi dan ajudikasi di Komisi Informasi? | UU 14/2008 P40, P42 |

## B. UU 25/2009 (Pelayanan Publik)

| ID | Type | Question | Gold pasal |
|---|---|---|---|
| Q021 | EXP | Apa saja hak masyarakat dalam pelayanan publik? | UU 25/2009 P18 |
| Q022 | EXP | Apa saja komponen yang harus ada dalam standar pelayanan? | UU 25/2009 P21 |
| Q023 | EXP | Apa itu maklumat pelayanan? | UU 25/2009 P22 |
| Q024 | EXP | Apa kewajiban penyelenggara dalam mengelola pengaduan? | UU 25/2009 P36, P37 |
| Q025 | EXP | Apa saja yang dilarang bagi pelaksana pelayanan publik? | UU 25/2009 P17 |
| Q026 | SIT | Pengaduan saya ke kantor pelayanan tidak ditanggapi. Siapa yang bisa menerima pengaduan saya? | UU 25/2009 P40, P46 |
| Q027 | SIT | Berapa lama penyelenggara wajib memutuskan hasil pemeriksaan pengaduan? | UU 25/2009 P50 |
| Q028 | SIT | Pelayanan dari instansi merugikan saya. Apakah saya bisa menggugat ke PTUN? | UU 25/2009 P51 |
| Q029 | SIT | Apa peran Ombudsman dalam pengaduan pelayanan publik? | UU 25/2009 P46 |
| Q030 | SIT | Apa sanksi bagi pelaksana yang melanggar ketentuan pelayanan publik? | UU 25/2009 P41, P54 |

## C. UU 27/2022 (Pelindungan Data Pribadi)

| ID | Type | Question | Gold pasal |
|---|---|---|---|
| Q031 | EXP | Apa itu data pribadi yang bersifat spesifik? | UU 27/2022 P4 |
| Q032 | EXP | Apa saja hak subjek data pribadi? | UU 27/2022 P5-P13 |
| Q033 | EXP | Bagaimana cara menarik kembali persetujuan penggunaan data pribadi saya? | UU 27/2022 P9, P40 |
| Q034 | EXP | Kapan pengendali data wajib menghapus data pribadi? | UU 27/2022 P43 |
| Q035 | EXP | Bagaimana persetujuan pemrosesan data anak? | UU 27/2022 P25 |
| Q036 | SIT | Aplikasi tempat saya mendaftar mengalami kebocoran data. Apa kewajiban mereka? | UU 27/2022 P46 |
| Q037 | SIT | Sebuah perusahaan memakai data saya tanpa persetujuan. Apa hak saya? | UU 27/2022 P20, P22, P12 |
| Q038 | SIT | Seseorang mengumpulkan data pribadi orang lain untuk keuntungannya. Apa ancaman pidananya? | UU 27/2022 P65, P67 |
| Q039 | SIT | Saya minta data saya diperbaiki tapi pihak pengendali tidak merespons. Berapa batas waktunya? | UU 27/2022 P30 |
| Q040 | SIT | Apakah transfer data pribadi ke luar negeri diperbolehkan? | UU 27/2022 P56 |

## D. Cross-law questions

| ID | Type | Question | Gold pasal |
|---|---|---|---|
| Q041 | CROSS | Bolehkah Badan Publik membuka data pribadi seseorang kalau diminta lewat permohonan informasi publik? | UU 14/2008 P17; UU 27/2022 P4, P15 |
| Q042 | CROSS | Apakah Badan Publik juga wajib melindungi data pribadi warga yang dilayani? | UU 27/2022 P2, P19; UU 25/2009 P15 |
| Q043 | CROSS | Kantor pelayanan memasang CCTV di ruang tunggu. Apa aturan pelindungan data yang berlaku? | UU 27/2022 P17; UU 25/2009 P25 |
| Q044 | CROSS | Warga mengadukan pelayanan buruk dan menyertakan data pribadi. Bagaimana kerahasiaan pengaduan dijaga? | UU 25/2009 P49; UU 27/2022 P36 |

## E. Out-of-scope questions (the correct behaviour is to say the corpus does not cover it)

| ID | Type | Question | Gold pasal |
|---|---|---|---|
| Q045 | OOS | Berapa tarif resmi pembuatan SIM baru? | none |
| Q046 | OOS | Apa syarat mendirikan PT menurut undang-undang? | none |
| Q047 | OOS | Bagaimana cara mengajukan gugatan cerai? | none |

## Notes for the proposal

- Q011-Q018, Q026-Q030 and Q036-Q040 are situation questions, so they test the "describe a problem and get the relevant pasal" use case directly.
- Q041-Q044 need pasal from two laws. Report hit@k for these separately, because retrievers often find only one of the two.
- Q045-Q047 measure hallucination. A system that confidently cites a pasal here is failing.