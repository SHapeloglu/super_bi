# Claude.md â€” SuperBI Context

## KiÅŸi
powerbiegitimi.com â€” SuperBI geliÅŸtiricisi ve yÃ¶neticisi

## Proje
**SuperBI**: Self-hosted, full-stack Business Intelligence (Power BI / Qlik Sense
alternatifi). Hedef 4 mihenk taÅŸÄ±: (1) kolay kullanÄ±m, (2) kolay karmaÅŸÄ±k metrik
oluÅŸturma, (3) memory'de depolama, (4) memory'de veri seti iliÅŸkisi.

- Stack: FastAPI + SQLAlchemy, HTML/CSS/JS, Apache ECharts, SQLite (metadata)
- Deployment: Contabo VPS (`vmi3389964`, `superbi.bidanismanlik.com.tr`),
  systemd service (superbi.service), WorkingDirectory=/opt/superbi
- Databases: Oracle XE, MSSQL, MySQL, PostgreSQL (Docker container'lar)
- VPS kÄ±sÄ±tÄ±: 7.8GB RAM (swap baskÄ±sÄ± var), 66GB disk boÅŸ â€” mimari kararlar
  bu kÄ±sÄ±tÄ± gÃ¶z Ã¶nÃ¼nde bulundurmalÄ±
- GitHub: https://github.com/SHapeloglu/super_bi (public, main branch) â€”
  README.md ve docs/ klasÃ¶rÃ¼ gÃ¼ncel tutuluyor

## Tercihler
- TÃ¼rkÃ§e iletiÅŸim
- Claude kendi Ã¶nerileri yapsÄ±n (aÃ§Ä±k uÃ§lu seÃ§im sunmasÄ±n)
- Sequential task completion â€” hatasÄ±z, en kÄ±sa/kolay iÅŸ Ã¶nce
- Sunucuya SSH ile baÄŸlÄ±, komutlarÄ± Claude Ã¼retir kullanÄ±cÄ± Ã§alÄ±ÅŸtÄ±rÄ±r
  (Claude'un doÄŸrudan sunucu eriÅŸimi yok, sadece izole sandbox'Ä± var)
- Yeni dosya/kod Ã¶ncen sandbox'ta test edilir, sonra deploy komutu Ã¼retilir
- Uzun/Ã¶zel karakterlioÄŸ dosyalar sunucuya heredoc yerine base64 ile aktarÄ±lÄ±r
  (TÃ¼rkÃ§e karakter/backtick sorunlarÄ± heredoc'ta yaÅŸanmÄ±ÅŸtÄ±)

## Bilinen kÄ±rÄ±lganlÄ±klar
- SBX compiler'da parantez Ã¶nceliÄŸi bug'qH[[™H
Œ‹LLÊH8 %Y\™[Bˆ0ï™[[H[XHÕS•PÕVPHS°çˆTÖHQ2,QQ2,
šŞ‹ˆPÒÓÑË›YXÚ[XYJB‹H^™\ÜÚ[Û—ØZ[\‹œHPSPÕÓPTÛÛ›™XİÜ—Ü™YÚ\İKœH’U‘T—ÓPT[BˆÙ[šÜ›Ûˆ][X[1,H
Ù^H\Ú[[\šH˜\šÛ1,HÛXš[\ˆœÜİÜ™\Ü[ˆœÈœÜİÜ™\ÈŠB‹HÛ]YIİ[ˆÙX—Ù™]Ú\˜Xñ,HÚ]XˆØ^Y˜[\±,[±,H˜^™[ˆ\ÚÚH
ØXÚIÛ[›ZqgÊBˆğíœİ\™Xš[^[Üˆ8 %Ú]ÙËÛË\™[[İH\ÚØ\±gñ,[qgİ1,\›X\ñ,Hğï™[š[\ˆñ'Ü[[XHpí›[ZB