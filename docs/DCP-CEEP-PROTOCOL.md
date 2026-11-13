# DCP-CEEP v1.0

## Continuous Execution & Evidence Protocol

**Repository:** `phakphum12345/development_control_platform`  
**Protocol type:** End-to-End Execution / Evidence / Continuity  
**Status:** Adopted — Central operating protocol for all Work Packages and pull requests

---

## 1. เป้าหมาย

สร้างระบบการทำงานต่อเนื่องที่สามารถพัฒนา ตรวจสอบ แก้ไข ทดสอบ และส่งมอบงานทั้ง Repository โดยไม่ทำให้ข้อมูลระหว่างทางสูญหาย

หลักการสำคัญ:

- ไม่ลดระดับรายละเอียดของรายงานเมื่อทำงานต่อเนื่อง
- ไม่ถือว่างานเสร็จหากไม่มีหลักฐาน
- ไม่ทำงานเดิมซ้ำโดยไม่มีเหตุผล
- ไม่ข้ามงานที่ยัง FAIL, UNKNOWN หรือ SKIPPED
- ไม่สร้างความสำเร็จที่ไม่มีหลักฐานรองรับ
- ไม่ Merge โดยไม่มีการอนุมัติที่จำเป็น

## 2. Execution State Protocol

ทุก Work Package ต้องมีสถานะหนึ่งในห้าระดับเท่านั้น:

| Status | ความหมาย |
|---|---|
| PASS | ตรวจสอบและมีหลักฐานครบ |
| FAIL | ตรวจพบข้อผิดพลาด |
| SKIPPED | ไม่ได้ดำเนินการหรือทดสอบ |
| UNKNOWN | ไม่มีหลักฐานเพียงพอ |
| IN_PROGRESS | กำลังดำเนินงาน |

ห้ามแปลง SKIPPED หรือ UNKNOWN เป็น PASS

## 3. Repository Baseline Lock

ก่อนเริ่มทุก PR ต้องบันทึก:

- Repository และ branch
- Base SHA
- Head SHA
- PR number และสถานะ
- Mergeability
- Review approvals และ unresolved threads
- CI workflow และ job status
- Files changed และ change summary

เมื่อ Head SHA เปลี่ยน ต้องตรวจสอบ CI ใหม่บน SHA ล่าสุดเสมอ

## 4. Continuous Execution Loop

ดำเนินงานตามลำดับ:

1. Recon — ตรวจสถานะ Repository และงานค้าง
2. Inventory — สำรวจไฟล์ โมดูล API และระบบที่มีอยู่
3. Gap Analysis — ระบุสิ่งที่ยังขาดและข้อผิดพลาด
4. Planning — แบ่งงานเป็น Work Packages
5. Implementation — พัฒนาโดยไม่ทำลายระบบเดิม
6. Testing — ทดสอบ unit, integration, regression และ platform
7. Evidence — รวบรวมผลตรวจและบันทึกหลักฐาน
8. Review — ตรวจ diff, security, compatibility และ scope
9. PR — สร้างหรือปรับปรุง PR
10. Merge Gate — รอ CI ผ่านและการอนุมัติที่จำเป็น
11. Post-Merge — ตรวจ merge commit และ main branch
12. Next Work — เริ่ม Work Package ถัดไปทันทีเมื่อเงื่อนไขครบ

หากพบ FAIL ให้แก้ไขและทดสอบซ้ำก่อนเดินหน้าผ่าน Gate นั้น

## 5. Resilience Protocol

ทุกกระบวนการที่เขียนไฟล์หรือเปลี่ยนสถานะต้องมี:

- Checkpoint ก่อนเริ่มงาน
- Atomic write เมื่อเหมาะสม
- ตรวจสอบไฟล์หลังเขียน
- Retry แบบจำกัดจำนวนครั้ง
- Backoff เมื่อพบ network หรือ connection error
- ตรวจสอบ idempotency ก่อน retry
- Recovery เมื่อ process หยุดกลางทาง
- บันทึก error และจุดที่หยุด
- ห้ามรายงานว่าสำเร็จหากยังไม่ได้ตรวจผลลัพธ์

การ reconnect ต้องกลับไปทำงานจาก checkpoint ที่ตรวจสอบได้ ไม่เริ่มซ้ำโดยไม่ตรวจสอบสถานะก่อน

## 6. Documentation Protocol

ทุก Work Package ต้องปรับปรุงเอกสารที่เกี่ยวข้อง:

- README
- Roadmap
- Implementation Status
- Requirements Traceability
- Architecture / Module / API documentation
- Test and Verification Evidence
- Documentation Index

เอกสารต้องบอกทั้งสิ่งที่ทำแล้ว สิ่งที่ยังขาด ข้อจำกัด และหลักฐานอ้างอิง

ห้ามเขียนว่า Complete หากยังมี operational acceptance หรือ platform validation ที่ไม่ได้ทำ

## 7. Reporting Protocol — ห้ามลดรายละเอียด

ทุกครั้งที่รายงานต้องมีหัวข้อดังนี้:

1. Repository Overview
2. Overall Progress
3. Completed Work Packages
4. Current Work Package
5. PR and Commit Evidence
6. CI Matrix and Test Results
7. FAIL / UNKNOWN / SKIPPED
8. Blockers and Root Causes
9. Corrective Actions
10. Remaining Roadmap
11. Merge Authorization Status
12. Next Execution Step

ห้ามย่อรายงานเหลือเพียงบรรทัดเดียวเมื่อมีงานที่กำลังดำเนินการหรือมีประเด็นที่ต้องติดตาม

## 8. Merge Safety Gate

อนุญาต Merge เมื่อ:

- PR เป็น PR ที่ตรวจสอบแล้ว
- Base และ Head SHA ถูกต้อง
- Mergeability เป็น TRUE
- CI ที่จำเป็นผ่านบน Head SHA ล่าสุด
- ไม่มี unresolved review thread ที่ยังต้องแก้
- ไม่มี review request หรือ approval requirement ที่ยังไม่ครบ
- ไม่มีการเปลี่ยนแปลงนอก scope ที่ไม่ได้ตรวจสอบ
- มีการอนุมัติ Merge จากผู้ใช้ตามขอบเขตที่กำหนด

ห้าม Merge เพียงเพราะ PR เปิดอยู่หรือมีบาง workflow ผ่าน

## 9. Scope and Safety

- ห้ามลบข้อมูลหรือไฟล์โดยไม่มีการอนุมัติ
- ห้ามเปิดเผย secrets หรือ credentials
- ห้ามสร้าง billable cloud resources โดยไม่มีการอนุมัติ
- ใช้ local-first และ self-hosted เมื่อเหมาะสม
- ห้ามกล่าวอ้างว่า CI แทนการทดสอบบนเครื่องจริงได้
- ห้ามรายงาน process cleanup หรือ OS isolation ว่าผ่าน หากไม่มีหลักฐานจริง

## 10. Continuity Ledger

ทุกครั้งที่จบหนึ่งรอบ ต้องบันทึก:

- Last completed Work Package
- Current Work Package
- Last verified Head SHA
- Last verified CI run
- Outstanding blockers
- Pending approvals
- Next exact action

การเริ่มรอบใหม่ต้องอ่าน Continuity Ledger ก่อนเริ่มดำเนินงาน

## 11. Completion Definition

Repository จะถือว่า End-to-End Complete ได้เมื่อ:

- ทุก roadmap item มีผลตรวจสอบ
- ไม่มีงานสำคัญที่ถูกละทิ้งโดยไม่ระบุเหตุผล
- Critical tests ผ่าน
- Security และ safety gates ผ่าน
- Documentation ครบและสอดคล้องกับ implementation
- Operational limitations ถูกเปิดเผย
- Main branch และ merge history ตรวจสอบได้
- Remaining work ถูกระบุอย่างชัดเจน

**หลักการสุดท้าย: งานต้องเดินหน้าด้วยหลักฐาน ไม่ใช่เดินหน้าด้วยคำรายงาน**
